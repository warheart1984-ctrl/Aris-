"""
cogos_runtime.py — CoGOS Governed Cognitive Runtime (Phase 0)

PID1-ready glue: GRE + Nova + UL substrate + Pattern Ledger + Λ cycle adapter.
"""

from __future__ import annotations

import os
import sys
import uuid
import json
import contextlib
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_RUNTIME = Path(__file__).resolve().parent
_ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))


def _ensure_paths() -> None:
    for p in (_RUNTIME, _RUNTIME / "ul", _RUNTIME / "voss", _ROOT):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


_ensure_paths()

from adapter_cycle_context import apply_drift_to_cycle, seed_cycle_from_drift  # noqa: E402
from governance_invariant_engine import (  # noqa: E402
    GovernanceRuntimeEngine,
    ModuleContract,
    build_execution_context,
    build_gre,
    cogos_root,
)
from nova_layer import NovaLayer, NovaOutput  # noqa: E402
from pattern_ledger import PatternLedger  # noqa: E402
from user_profiles import UserProfileManager  # noqa: E402
from creative_modules import run_creative  # noqa: E402
from compute_tiers import ComputeTierEngine  # noqa: E402
from automatic_mode import AutomaticModeEngine  # noqa: E402

try:
    from voss.voss_binding import CycleContext
except ImportError:
    from voss_binding import CycleContext  # type: ignore


def _load_ul_substrate():
    from creative_substrate import register_creative_handlers
    from ul_stdlib_substrate import apply_stdlib_verbs_to_substrate, register_stdlib_handlers
    from ul_substrate import Capability, ForgeGate, SubstrateRuntime

    apply_stdlib_verbs_to_substrate()
    runtime = SubstrateRuntime(gate=ForgeGate())
    register_creative_handlers(runtime)
    register_stdlib_handlers(runtime)
    return runtime


class CognitiveRuntime:
    CORE_MODULES = ("Nova", "Jarvis", "ULVM", "PatternLedger", "Forge", "PID1")

    def __init__(self) -> None:
        self.gre: GovernanceRuntimeEngine = build_gre()
        self.nova = NovaLayer()
        self.profiles = UserProfileManager()
        self.tiers = ComputeTierEngine()
        self.automatic = AutomaticModeEngine()
        self.ul = _load_ul_substrate()
        self.ledger = PatternLedger()
        self.mode = self.profiles.get_active().mode_default
        self.booted = False
        self.cycle_ctx: Optional[CycleContext] = None

    def boot(self) -> bool:
        if self.booted:
            return True

        root = cogos_root()
        for rel in (
            "law/root_law.json",
            "law/governance_rules.json",
            "law/law_manifest.json",
        ):
            if not (root / rel).exists():
                print(f"[PID1] BOOT FAILED: missing {rel}")
                return False

        self._register_core_contracts()
        profile = self.profiles.get_active()
        self.mode = profile.mode_default
        self.nova.set_profile(profile.id, profile.extra_ward_patterns())
        self.nova.load_identity_anchor()

        boot_ctx = build_execution_context(
            self.gre,
            "PID1",
            {
                "action": "boot",
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            lane_id="BOOT",
            subject="CoGOS",
            declared_bindings=["Λ.1", "Λ.2", "Λ.3", "Λ.6", "Λ.7"],
        )
        result = self.gre.enforce(boot_ctx, mode=self.mode)
        self._commit_ledger(result)

        if not result.passed:
            print(f"[PID1] BOOT FAILED: {[v.description for v in result.violations]}")
            return False

        self.cycle_ctx = seed_cycle_from_drift(boot_ctx.drift_scores, state="1001")
        self.booted = True
        print("[PID1] CoGOS Booted — Governance Active. Nova Online. Infi Law Enforced.")
        return True

    def _register_core_contracts(self) -> None:
        contracts = [
            ModuleContract(
                module_id="Nova",
                lane_id="HUMAN_PARTNER",
                subject="Nova",
                required_input_fields=["command"],
                governance_bindings=["Λ.2", "Λ.4", "Λ.5", "Λ.7"],
                allowed_subjects=["Nova"],
            ),
            ModuleContract(
                module_id="ULVM",
                lane_id="UL_EXEC",
                subject="Nova",
                required_input_fields=["action"],
                governance_bindings=["Λ.1", "Λ.2", "Λ.3"],
                allowed_subjects=["Nova", "Jarvis", "ULVM"],
            ),
            ModuleContract(
                module_id="Jarvis",
                lane_id="RUNTIME",
                subject="Jarvis",
                governance_bindings=["Λ.1", "Λ.2", "Λ.7"],
                allowed_subjects=["Jarvis"],
            ),
            ModuleContract(
                module_id="PID1",
                lane_id="BOOT",
                subject="CoGOS",
                governance_bindings=["Λ.1", "Λ.2", "Λ.3", "Λ.6", "Λ.7"],
                allowed_subjects=["CoGOS"],
            ),
            ModuleContract(
                module_id="Creative",
                lane_id="CREATIVE",
                subject="Nova",
                required_input_fields=["lane", "verb"],
                governance_bindings=["Λ.1", "Λ.2", "Λ.3", "Λ.5"],
                allowed_subjects=["Nova", "Jarvis"],
            ),
            ModuleContract(
                module_id="Mesh",
                lane_id="MESH",
                subject="CoGOS",
                governance_bindings=["Λ.2", "Λ.4", "Λ.7"],
                allowed_subjects=["CoGOS", "Nova"],
            ),
            ModuleContract(
                module_id="AutomaticMode",
                lane_id="AUTOMATIC",
                subject="Nova",
                required_input_fields=["action"],
                governance_bindings=["Λ.1", "Λ.2", "Λ.3", "Λ.7"],
                allowed_subjects=["Nova", "Jarvis", "CoGOS"],
            ),
        ]
        for c in contracts:
            self.gre.register_module(c)

    def _commit_ledger(self, result) -> None:
        if result.audit_record:
            self.ledger.append_audit(result.audit_record)

    def process(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not self.booted and not self.boot():
            return "BOOT FAILED — Governance violation."

        ctx = dict(context or {})
        ctx["mode"] = self.mode
        nova_out = self.nova.generate_response(user_input, self.mode, ctx)

        if ctx.get("needs_automatic"):
            automatic_result = self._run_automatic_governed(ctx)
            if automatic_result.startswith("GOVERNANCE BLOCK"):
                return automatic_result
            return f"{nova_out.text}\n{automatic_result}"

        if ctx.get("needs_creative"):
            creative_result = self._run_creative_governed(
                ctx.get("creative_lane", "story_forge"),
                ctx.get("creative_verb", "drafts"),
                ctx.get("creative_prompt", user_input),
                ctx,
            )
            if creative_result.startswith("GOVERNANCE BLOCK"):
                return creative_result
            return f"{nova_out.text}\n{creative_result}"

        if ctx.get("needs_ul"):
            ul_result = self._run_ul_governed(ctx.get("ul_source", user_input))
            if ul_result.startswith("GOVERNANCE BLOCK"):
                return ul_result
            return f"{nova_out.text}\n{ul_result}"

        return nova_out.text

    def _run_automatic_governed(self, ctx: Dict[str, Any]) -> str:
        action = str(ctx.get("automatic_action") or "status")
        cap = {
            "workspace": "automatic.workspace",
            "organize": "automatic.organize_apply" if ctx.get("organize_apply") else "automatic.organize_plan",
            "remember": "automatic.remember",
            "suggest": "automatic.suggest",
            "status": "automatic.status",
        }.get(action, "automatic.status")

        tier_check = self.tiers.check(cap, profile_id=self.profiles.active_id)
        if not tier_check.allowed:
            self.tiers.log_denial(tier_check, context={"action": action})
            return f"GOVERNANCE BLOCK (tier): {tier_check.reason}"

        exec_ctx = build_execution_context(
            self.gre,
            "AutomaticMode",
            {
                "action": action,
                "capability": cap,
                "profile": self.profiles.active_id,
                "mode": self.mode,
            },
            lane_id=f"automatic-{action}",
            subject="Nova",
        )

        def _execute(context):
            if action == "workspace":
                return self.automatic.create_workspace(
                    str(ctx.get("workspace_name") or "New Workspace"),
                    profile_id=self.profiles.active_id,
                )
            if action == "organize":
                return self.automatic.organize_files(
                    str(ctx.get("organize_source") or "."),
                    workspace_id=ctx.get("workspace_id"),
                    apply=bool(ctx.get("organize_apply")),
                )
            if action == "remember":
                return self.automatic.remember(
                    str(ctx.get("memory_key") or "note"),
                    str(ctx.get("memory_value") or ""),
                    workspace_id=ctx.get("workspace_id"),
                )
            if action == "suggest":
                return self.automatic.suggest_workflows()
            return self.automatic.status()

        result = self.gre.enforce(exec_ctx, execute=_execute, mode=self.mode)
        self._commit_ledger(result)
        if not result.passed:
            desc = result.violations[0].description if result.violations else "unknown"
            return f"GOVERNANCE BLOCK: {desc}"
        out = result.output or {}
        if not out.get("ok", True):
            return f"GOVERNANCE BLOCK: {out.get('reason', 'automatic action failed')}"
        return self._format_automatic_output(action, out)

    def _format_automatic_output(self, action: str, out: Dict[str, Any]) -> str:
        if action == "workspace":
            ws = out.get("workspace", {})
            return f"AUTOMATIC OK: workspace '{ws.get('name')}' ready at {ws.get('path')}"
        if action == "organize":
            count = out.get("moved") if out.get("apply") else out.get("planned")
            verb = "moved" if out.get("apply") else "planned"
            return f"AUTOMATIC OK: {verb} {count} files from {out.get('source')} into {out.get('target_root')}"
        if action == "remember":
            return f"AUTOMATIC OK: remembered {out.get('key')} for {out.get('workspace_id') or 'global'}"
        if action == "suggest":
            return f"AUTOMATIC OK: {len(out.get('suggestions', []))} workflow suggestions ready"
        return (
            f"AUTOMATIC OK: {out.get('workspace_count', 0)} workspaces, "
            f"{out.get('memory_buckets', 0)} memory buckets, "
            f"{out.get('suggestions_count', 0)} suggestions"
        )

    def _run_creative_governed(
        self,
        lane: str,
        verb: str,
        prompt: str,
        ctx: Dict[str, Any],
    ) -> str:
        tier_check = self.tiers.check_creative(lane, verb, profile_id=self.profiles.active_id)
        if not tier_check.allowed:
            self.tiers.log_denial(tier_check, context={"lane": lane, "verb": verb})
            return f"GOVERNANCE BLOCK (tier): {tier_check.reason}"

        exec_ctx = build_execution_context(
            self.gre,
            "Creative",
            {
                "lane": lane,
                "verb": verb,
                "prompt": prompt[:500],
                "profile": self.profiles.active_id,
            },
            lane_id=f"creative-{lane}",
            subject="Nova",
        )

        def _execute(context):
            r = run_creative(lane, verb, prompt=prompt, context=ctx)
            return {
                "ok": r.ok,
                "summary": r.summary,
                "artifact_path": r.artifact_path,
                "details": r.details,
            }

        result = self.gre.enforce(exec_ctx, execute=_execute, mode=self.mode)
        self._commit_ledger(result)
        if not result.passed:
            desc = result.violations[0].description if result.violations else "unknown"
            return f"GOVERNANCE BLOCK: {desc}"
        out = result.output or {}
        if not out.get("ok"):
            return f"GOVERNANCE BLOCK: {out.get('summary', 'creative failed')}"
        return f"CREATIVE OK [{lane}]: {out.get('summary')} → {out.get('artifact_path', '')}"

    def _run_ul_governed(self, source: str) -> str:
        preview_cap = "dangerous"
        lower = source.lower()
        for verb in ("deletes", "removes", "purges", "shutdown", "terminates", "delete_repo"):
            if verb in lower:
                preview_cap = "dangerous"
                break
        else:
            preview_cap = "harmless"

        tier_check = self.tiers.check_ul_capability(preview_cap, profile_id=self.profiles.active_id)
        if not tier_check.allowed:
            self.tiers.log_denial(tier_check, context={"source": source[:200]})
            return f"GOVERNANCE BLOCK (tier): {tier_check.reason}"

        exec_ctx = build_execution_context(
            self.gre,
            "ULVM",
            {"action": "substrate_execute", "source": source, "capability": preview_cap},
            lane_id=str(uuid.uuid4())[:12],
            subject="Nova",
        )

        def _execute(context):
            from ul_substrate import Capability, ForgeGate

            if self.mode == "manual":
                self.ul.gate = ForgeGate(blocked_capabilities={Capability.PRIVILEGED})
            else:
                self.ul.gate = ForgeGate()
            operator = self.mode == "manual"
            result = self.ul.execute(
                source,
                context={"mode": self.mode, "profile": self.profiles.active_id},
                operator_present=operator,
            )
            return {
                "allowed": result.allowed,
                "outputs": result.outputs,
                "audit_len": len(result.audit),
                "error": result.error,
            }

        result = self.gre.enforce(exec_ctx, execute=_execute, mode=self.mode)
        self._commit_ledger(result)

        if self.cycle_ctx and exec_ctx.drift_scores:
            apply_drift_to_cycle(self.cycle_ctx, exec_ctx.drift_scores)

        if not result.passed:
            desc = result.violations[0].description if result.violations else "unknown"
            return f"GOVERNANCE BLOCK: {desc}"

        out = result.output or {}
        if not out.get("allowed", True):
            return "GOVERNANCE BLOCK: substrate ForgeGate denied execution"
        outputs = out.get("outputs") or []
        return f"UL OK: {outputs if outputs else 'executed (no output)'}"

    def set_mode(self, mode: str) -> None:
        if mode in ("automatic", "manual"):
            self.mode = mode
            print(f"[CoGOS] Mode switched to {mode} (governed)")

    def switch_profile(self, profile_id: str) -> None:
        self.profiles.set_active(profile_id)
        profile = self.profiles.get_active()
        self.mode = profile.mode_default
        self.nova.set_profile(profile.id, profile.extra_ward_patterns())
        print(f"[CoGOS] Active profile: {profile.display_name} (mode={self.mode})")

    def status(self) -> Dict[str, Any]:
        return {
            "booted": self.booted,
            "mode": self.mode,
            "profile": self.profiles.active_id,
            "profiles": self.profiles.list_profiles(),
            "anchor": self.nova.anchor,
            "ledger_entries": len(self.ledger.list_entries(1000)),
            "ledger_verify": self.ledger.verify_chain(),
            "gre_audit_len": len(self.gre.audit_chain),
            "cycle_state": self.cycle_ctx.current_state if self.cycle_ctx else None,
            "stability": self.cycle_ctx.stability_score if self.cycle_ctx else None,
            "compute_tier": self.tiers.resolve_tier(self.profiles.active_id),
            "automatic": self.automatic.status(),
        }


def repl() -> None:
    runtime = CognitiveRuntime()
    if not runtime.boot():
        sys.exit(1)
    print("CoGOS Nova REPL — type 'exit' to quit. 'mode manual' | 'status' | 'substrate: agent pings x1'")
    while True:
        try:
            cmd = input("nova> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not cmd:
            continue
        if cmd.lower() == "exit":
            break
        if cmd.startswith("mode "):
            runtime.set_mode(cmd.split(maxsplit=1)[1].strip().lower())
            continue
        if cmd.startswith("profile "):
            runtime.switch_profile(cmd.split(maxsplit=1)[1].strip().lower())
            continue
        if cmd.lower() == "status":
            import json

            print(json.dumps(runtime.status(), indent=2))
            continue
        print(runtime.process(cmd))


def proof() -> Dict[str, Any]:
    runtime = CognitiveRuntime()
    with contextlib.redirect_stdout(io.StringIO()):
        boot_ok = runtime.boot()
    status = runtime.status()
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": boot_ok,
        "runtime": status,
        "root": str(cogos_root()),
        "proof_type": "cogos_runtime",
    }


def main() -> None:
    if "--proof" in sys.argv:
        print(json.dumps(proof(), indent=2, sort_keys=True))
        return
    repl()


if __name__ == "__main__":
    main()
