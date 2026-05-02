from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import difflib
import json
from pathlib import Path
from typing import Any
import uuid

from src.forge_client import LawBoundForgeClient
from src.forge_eval_client import LawBoundForgeEvalClient
from src.jarvis_operator import JarvisOperator
from src.law_context_builder import RuntimeLawContext
from src.runtime_law import RuntimeLaw

from .hall_of_discard import HallOfDiscard
from .hall_of_fame import HallOfFame
from .hall_of_shame import HallOfShame
from .evolve_engine import EvolveEngineTraceStore
from .integrity import ProtectedComponentIntegrity
from .jarvis_blueprint import BLUEPRINT_ID, JarvisBlueprintReasoner
from .kill_switch import ArisKillSwitch
from .cognitive_upgrade import CognitiveUpgradeManager
from .log_ingestion import (
    build_forge_eval_request,
    classify_evaluation,
    extract_candidates,
    normalize_codex_log,
)
from .logbook import RepoLogbook
from .memory_bank import GovernedMemoryBank
from .shield import DecisionContext, ShieldOfTruth1001, Verdict as ShieldVerdict

try:
    from .mystic import MysticReflectionRuntime, MysticSustainmentService
except Exception as exc:  # pragma: no cover - startup fallback only.
    MysticSustainmentService = None  # type: ignore[assignment]
    MysticReflectionRuntime = None  # type: ignore[assignment]
    _MYSTIC_IMPORT_ERROR: Exception | None = exc
    _MYSTIC_REFLECTION_IMPORT_ERROR: Exception | None = exc
else:
    _MYSTIC_IMPORT_ERROR = None
    _MYSTIC_REFLECTION_IMPORT_ERROR = None

try:
    from forge.service import ForgeService
except Exception as exc:  # pragma: no cover - startup fallback only.
    ForgeService = None  # type: ignore[assignment]
    _FORGE_IMPORT_ERROR: Exception | None = exc
else:
    _FORGE_IMPORT_ERROR = None

try:
    from forge_eval.service import ForgeEvalService
except Exception as exc:  # pragma: no cover - startup fallback only.
    ForgeEvalService = None  # type: ignore[assignment]
    _FORGE_EVAL_IMPORT_ERROR: Exception | None = exc
else:
    _FORGE_EVAL_IMPORT_ERROR = None


META_LAW_1001 = {
    "id": "1001",
    "title": "1001 Meta Law",
    "summary": (
        "All valid system behavior must begin under law, pass through non-bypassable "
        "validation, and only return if verified."
    ),
}

FOUNDATION_LAW = {
    "id": "foundation",
    "title": "Foundation Law",
    "summary": (
        "Safe adaptation only; failed code is rejected; unsafe outcomes are contained "
        "instead of silently progressing."
    ),
}

GUARDRAILS = (
    {
        "id": "declared_purpose",
        "title": "Declared Purpose",
        "summary": "Actions must declare a concrete in-contract purpose.",
    },
    {
        "id": "safe_adaptation",
        "title": "Safe Adaptation",
        "summary": "Unsafe, failed, hidden, unstable, or out-of-contract changes do not activate.",
    },
    {
        "id": "bounded_authority",
        "title": "Bounded Authority",
        "summary": "Authority stays external, bounded, and non-self-expanding.",
    },
    {
        "id": "observability",
        "title": "Observability",
        "summary": "Meaningful actions must remain visible, logged, and reviewable.",
    },
    {
        "id": "verified_escalation",
        "title": "Verified Escalation",
        "summary": "Risky paths require Forge Eval verification; Operator is not final authority.",
    },
)

RISKY_ACTION_TYPES = frozenset(
    {
        "python_execute",
        "command_execute",
        "file_write",
        "file_replace",
        "text_patch_apply",
        "patch_apply",
        "patch_hunk_apply",
        "patch_line_apply",
        "symbol_edit",
        "task_approval",
        "mutation_apply",
        "snapshot_restore",
        "workspace_import_upload",
        "workspace_repo_clone",
        "change_rollback",
    }
)

REPO_CHANGE_ACTION_TYPES = frozenset(
    {
        "file_write",
        "file_replace",
        "text_patch_apply",
        "patch_apply",
        "patch_hunk_apply",
        "patch_line_apply",
        "symbol_edit",
        "task_approval",
        "approval_resolution",
        "workspace_import_upload",
        "workspace_repo_clone",
        "change_rollback",
    }
)

REPO_TARGET_HINTS = (
    "evolving_ai/",
    "forge/",
    "forge_eval/",
    "tests/",
    "README.md",
    "LOGBOOK.md",
    "pyproject.toml",
    "run_aris.ps1",
)

PROTECTED_RUNTIME_RELATIVE_PATHS = (
    "evolving_ai/aris",
    "evolving_ai/app/server.py",
    "evolving_ai/app/service.py",
    "forge",
    "forge_eval",
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: object) -> str:
    return str(value or "").strip()


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _serialize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    return value


def _build_unified_diff(path: str, before: str, after: str) -> str:
    diff_lines = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    return "\n".join(diff_lines) or f"No textual diff for `{path}`."


@dataclass(slots=True)
class GovernanceDecision:
    action_id: str
    action_type: str
    purpose: str
    target: str
    source: str
    session_id: str
    operator_decision: str
    risky: bool
    requires_forge_eval: bool
    allowed: bool
    verified: bool
    disposition: str
    reason: str
    fingerprint: str
    blueprint_trace: dict[str, Any]
    law_results: list[dict[str, Any]]
    guardrails: list[dict[str, Any]]
    forge_eval: list[dict[str, Any]]
    integrity: dict[str, Any]
    reentry_blocker: dict[str, Any] | None
    kill_switch: dict[str, Any]
    action: dict[str, Any]
    created_at: str
    discard_entry: dict[str, Any] | None = None
    hall_name: str | None = None
    hall_entry: dict[str, Any] | None = None
    shield: dict[str, Any] | None = None
    mystic_signal: dict[str, Any] | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "purpose": self.purpose,
            "target": self.target,
            "source": self.source,
            "session_id": self.session_id,
            "operator_decision": self.operator_decision,
            "risky": self.risky,
            "requires_forge_eval": self.requires_forge_eval,
            "allowed": self.allowed,
            "verified": self.verified,
            "disposition": self.disposition,
            "reason": self.reason,
            "fingerprint": self.fingerprint,
            "blueprint_trace": _serialize(self.blueprint_trace),
            "law_results": _serialize(self.law_results),
            "guardrails": _serialize(self.guardrails),
            "forge_eval": _serialize(self.forge_eval),
            "integrity": _serialize(self.integrity),
            "reentry_blocker": _serialize(self.reentry_blocker),
            "kill_switch": _serialize(self.kill_switch),
            "hall_name": self.hall_name,
            "hall_entry": _serialize(self.hall_entry),
            "discard_entry": _serialize(self.discard_entry),
            "shield": _serialize(self.shield),
            "mystic_signal": _serialize(self.mystic_signal),
            "created_at": self.created_at,
        }


class ArisRuntime:
    """Unified ARIS law, evaluation, containment, and authority runtime."""

    def __init__(self, *, repo_root: Path, runtime_root: Path | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.runtime_root = (runtime_root or (self.repo_root / ".forge_chat" / "aris")).resolve()
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.activity_path = self.runtime_root / "activity.jsonl"
        self.logbook = RepoLogbook(self.repo_root / "LOGBOOK.md")
        self.memory_bank = GovernedMemoryBank(
            self.runtime_root / "memory_bank",
            foundation_root=self.runtime_root / "foundation",
        )
        self.runtime_law = RuntimeLaw(
            repo_root=self.repo_root,
            runtime_root=self.runtime_root,
            system_name="ARIS",
        )
        self.cognitive_upgrade = CognitiveUpgradeManager(
            history_path=self.runtime_root / "cognitive_upgrade" / "history.jsonl",
            doc_channel=self.runtime_law.doc_channel,
        )
        self.reasoner = JarvisBlueprintReasoner()
        self.shield_of_truth = ShieldOfTruth1001()
        self.hall_of_discard = HallOfDiscard(self.runtime_root / "hall_of_discard")
        self.hall_of_shame = HallOfShame(self.runtime_root / "hall_of_shame")
        self.hall_of_fame = HallOfFame(self.runtime_root / "hall_of_fame")
        self.evolve_engine = EvolveEngineTraceStore(self.runtime_root / "evolve_engine")
        self.kill_switch = ArisKillSwitch(self.runtime_root / "kill_switch")
        self.protected_paths = [
            (self.repo_root / relative).resolve() for relative in PROTECTED_RUNTIME_RELATIVE_PATHS
        ]
        self.integrity = ProtectedComponentIntegrity(
            manifest_path=self.runtime_root / "integrity-manifest.json",
            protected_paths=self.protected_paths,
        )
        self.operator_router = JarvisOperator(self.runtime_law)
        self.mystic = (
            MysticSustainmentService()
            if MysticSustainmentService is not None
            else None
        )
        self.mystic_reflection = (
            MysticReflectionRuntime()
            if MysticReflectionRuntime is not None
            else None
        )
        raw_forge = ForgeService() if ForgeService is not None else None
        raw_forge_eval = (
            ForgeEvalService(storage_root=self.runtime_root / "forge_eval")
            if ForgeEvalService is not None
            else None
        )
        self.forge = (
            LawBoundForgeClient(raw_forge, self.runtime_law)
            if raw_forge is not None
            else None
        )
        self.forge_eval = (
            LawBoundForgeEvalClient(raw_forge_eval, self.runtime_law)
            if raw_forge_eval is not None
            else None
        )
        self._startup = self._refresh_startup_state(lockdown_on_failure=True)

    def _decision_values(self, decision: GovernanceDecision) -> dict[str, Any]:
        return {
            "action_id": decision.action_id,
            "action_type": decision.action_type,
            "purpose": decision.purpose,
            "target": decision.target,
            "source": decision.source,
            "session_id": decision.session_id,
            "operator_decision": decision.operator_decision,
            "risky": decision.risky,
            "requires_forge_eval": decision.requires_forge_eval,
            "allowed": decision.allowed,
            "verified": decision.verified,
            "disposition": decision.disposition,
            "reason": decision.reason,
            "fingerprint": decision.fingerprint,
            "blueprint_trace": decision.blueprint_trace,
            "law_results": decision.law_results,
            "guardrails": decision.guardrails,
            "forge_eval": decision.forge_eval,
            "integrity": decision.integrity,
            "reentry_blocker": decision.reentry_blocker,
            "kill_switch": decision.kill_switch,
            "action": decision.action,
            "created_at": decision.created_at,
            "discard_entry": decision.discard_entry,
            "hall_name": decision.hall_name,
            "hall_entry": decision.hall_entry,
            "shield": decision.shield,
            "mystic_signal": decision.mystic_signal,
        }

    def _collect_startup_blockers(self, *, integrity: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if BLUEPRINT_ID != "jarvis.blueprint.aris-rebound":
            blockers.append("Jarvis blueprint inheritance is not rebound to the ARIS identity.")
        if not self.logbook.exists():
            blockers.append("Repo Logbook is missing, so meaningful changes cannot verify under 1001.")
        if self.shield_of_truth is None:
            blockers.append("Shield of Truth is unavailable.")
        if self.mystic is None:
            blockers.append(
                "Mystic sustainment is unavailable. "
                + (_text(_MYSTIC_IMPORT_ERROR) or "The ARIS sustainment module could not be imported.")
            )
        if self.mystic_reflection is None:
            blockers.append(
                "Mystic Reflection is unavailable. "
                + (
                    _text(_MYSTIC_REFLECTION_IMPORT_ERROR)
                    or "The Jarvis-merged Mystic reflection component could not be imported."
                )
            )
        if self.forge is None:
            blockers.append(
                "Forge is unavailable. "
                + (_text(_FORGE_IMPORT_ERROR) or "The Forge contractor package could not be imported.")
            )
        if self.forge_eval is None:
            blockers.append(
                "Forge Eval is unavailable. "
                + (
                    _text(_FORGE_EVAL_IMPORT_ERROR)
                    or "The Forge Eval authority package could not be imported."
                )
            )
        if not (self.runtime_root / "hall_of_discard").exists():
            blockers.append("Hall of Discard storage could not be created.")
        if not integrity.get("ok", False):
            blockers.append("Protected component integrity failed during startup.")
        return blockers

    def _record_startup_shame(
        self,
        *,
        blockers: list[str],
        integrity: dict[str, Any],
    ) -> None:
        diagnostic_json = json.dumps(
            {"blockers": blockers, "integrity": integrity},
            sort_keys=True,
        )
        fingerprint = self._fingerprint_for_action(
            action_type="startup_activation",
            purpose="Initialize ARIS under bound law and protected integrity.",
            target=str(self.repo_root),
            patch="",
            command=[],
            code=diagnostic_json,
            metadata={"source": "startup", "session_id": "system"},
        )
        self._shame(
            fingerprint=fingerprint,
            action={
                "action_id": "startup_activation",
                "action_type": "startup_activation",
                "purpose": "Initialize ARIS under bound law and protected integrity.",
                "target": str(self.repo_root),
                "source": "startup",
                "session_id": "system",
                "command": [],
            },
            reason="ARIS startup integrity or law binding failed.",
            law_results=[],
            guardrails=[],
            forge_eval=[],
            operator_decision="system",
            notes="Startup entered fail-closed lockdown because protected-law initialization failed.",
            metadata={"blockers": blockers, "integrity": integrity},
        )

    def _refresh_startup_state(
        self,
        *,
        lockdown_on_failure: bool,
        reseal_integrity: bool = False,
    ) -> dict[str, Any]:
        integrity = self.integrity.verify_or_initialize(reseal=reseal_integrity)
        blockers = self._collect_startup_blockers(integrity=integrity)
        if blockers:
            if lockdown_on_failure:
                self.kill_switch.lockdown(
                    reason="startup_law_integrity_failure",
                    actor="startup",
                    diagnostics={
                        "blockers": blockers,
                        "integrity": integrity,
                    },
                    startup_blocker=True,
                )
                self._record_startup_shame(blockers=blockers, integrity=integrity)
        state = {
            "startup_ready": not blockers,
            "startup_blockers": blockers,
            "integrity": integrity,
            "initialized_at": _utc_now(),
        }
        self._startup = state
        return state

    def _record_activity(self, event: dict[str, Any]) -> None:
        payload = {"recorded_at": _utc_now(), **_serialize(event)}
        with self.activity_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def list_activity(self, *, limit: int = 25) -> list[dict[str, Any]]:
        if not self.activity_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.activity_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                events.append(record)
        bounded = max(1, min(int(limit), 200))
        return list(reversed(events[-bounded:]))

    def _recent_unsafe_escalations(self, *, limit: int = 20) -> int:
        count = 0
        for entry in self.list_activity(limit=limit):
            if (
                _text(entry.get("disposition")) in {"blocked", "discarded"}
                and _truthy(entry.get("risky"))
            ):
                count += 1
        return count

    def _sanitize_ingestion_packet(self, packet: dict[str, Any]) -> dict[str, Any]:
        return {
            str(key): _serialize(value)
            for key, value in dict(packet or {}).items()
            if key not in {"output_text", "output_excerpt", "raw_text", "raw_log"}
        }

    def _build_log_ingestion_action(
        self,
        *,
        packet: dict[str, Any],
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        request_payload = build_forge_eval_request(candidate, repo_root=str(self.repo_root))
        action_type = "patch_apply" if str(candidate.get("kind")) == "patch" else "python_execute"
        payload = dict(request_payload.get("payload") or {})
        return {
            "action_id": str(candidate.get("candidate_id") or ""),
            "action_type": action_type,
            "session_id": _text(packet.get("session_id")) or "codex-log",
            "purpose": (
                "Normalize, evaluate, classify, and store a Codex log candidate under ARIS law "
                "before it may become reusable experience."
            ),
            "target": _text(candidate.get("target")),
            "source": "codex_log",
            "operator_decision": "approved",
            "patch": str(payload.get("patch") or ""),
            "code": str(payload.get("program") or ""),
            "command": [],
            "authorized": True,
            "observed": True,
            "bounded": True,
        }

    def list_evolve_traces(self, *, limit: int = 25) -> list[dict[str, Any]]:
        return self.evolve_engine.list_entries(limit=limit)

    def ingest_codex_log(
        self,
        raw_log: Any,
        *,
        session_id: str = "codex-log",
        source: str = "codex",
    ) -> dict[str, Any]:
        packet = normalize_codex_log(raw_log, source=source, session_id=session_id)
        sanitized_packet = self._sanitize_ingestion_packet(packet)
        self.runtime_law.ledger.record(
            "log_ingestion_normalized",
            {"packet": sanitized_packet},
            require_success=True,
        )
        candidates = extract_candidates(packet)
        outcomes: list[dict[str, Any]] = []
        if not candidates:
            result = {
                "ok": True,
                "packet": sanitized_packet,
                "candidate_count": 0,
                "results": [],
                "counts": {"FAME": 0, "SHAME": 0, "DISGRACE": 0},
            }
            self._record_activity({**result, "kind": "codex_log_ingestion"})
            return result

        for candidate in candidates:
            self.runtime_law.ledger.record(
                "log_ingestion_candidate",
                {"packet_id": packet["packet_id"], "candidate": _serialize(candidate)},
                require_success=True,
            )
            action = self._build_log_ingestion_action(packet=packet, candidate=candidate)
            decision = self.review_action(action)
            evaluation: dict[str, Any]
            hall_name = _text(decision.hall_name)
            hall_entry = decision.hall_entry
            finalized = decision

            if decision.allowed:
                forge_eval_entry = next((item for item in decision.forge_eval if isinstance(item, dict)), {})
                evaluation = classify_evaluation(
                    dict(forge_eval_entry.get("raw") or {}),
                    status_code=int(forge_eval_entry.get("status_code", 0) or 0),
                )
                if evaluation["classification"] == "FAME":
                    finalized = self.finalize_action(
                        decision,
                        result={
                            "ok": True,
                            "verification_artifacts": [
                                {
                                    "type": "forge_eval",
                                    "status_code": evaluation["status_code"],
                                    "score": evaluation["score"],
                                },
                                {
                                    "type": "doc_channel",
                                    "namespace": self.runtime_law.doc_channel.namespace,
                                    "version": self.runtime_law.doc_channel.version,
                                },
                            ],
                            "normalized_packet": sanitized_packet,
                            "candidate": _serialize(candidate),
                            "evaluation": _serialize(evaluation),
                            "classification": evaluation["classification"],
                        },
                    )
                    hall_name = _text(finalized.hall_name)
                    hall_entry = finalized.hall_entry
                    if not finalized.verified or hall_name != "hall_of_fame":
                        evaluation = {
                            **evaluation,
                            "classification": "DISGRACE",
                            "hall_name": hall_name or "hall_of_discard",
                            "reason": finalized.reason,
                        }
                else:
                    hall_name, hall_entry = self._record_failure_hall(
                        action=decision.action,
                        fingerprint=decision.fingerprint,
                        reason=evaluation["reason"],
                        law_results=decision.law_results,
                        guardrails=decision.guardrails,
                        forge_eval=decision.forge_eval,
                        operator_decision=decision.operator_decision,
                        notes=(
                            "Candidate was lawful enough to evaluate but did not reach the Fame threshold, "
                            "so it was preserved in Hall of Shame and kept out of live truth."
                        ),
                        failure_kind="correctness",
                        metadata={
                            "normalized_packet": sanitized_packet,
                            "candidate": _serialize(candidate),
                            "evaluation": _serialize(evaluation),
                        },
                    )
            else:
                forge_eval_entry = next((item for item in decision.forge_eval if isinstance(item, dict)), {})
                if forge_eval_entry:
                    evaluation = classify_evaluation(
                        dict(forge_eval_entry.get("raw") or {}),
                        status_code=int(forge_eval_entry.get("status_code", 0) or 0),
                    )
                else:
                    evaluation = {
                        "classification": "DISGRACE",
                        "hall_name": hall_name or "hall_of_discard",
                        "reason": decision.reason,
                        "score": 0.0,
                        "status_code": 0,
                        "violations": [],
                        "failed_checks": [],
                        "raw": {},
                    }
                hall_name = hall_name or _text(evaluation.get("hall_name")) or _text(
                    (decision.reentry_blocker or {}).get("hall")
                )
                hall_entry = hall_entry or decision.reentry_blocker

            trace_id = f"trace_{uuid.uuid4().hex[:12]}"
            trace_entry = self.evolve_engine.record(
                trace_id=trace_id,
                packet=sanitized_packet,
                candidate=_serialize(candidate),
                evaluation=_serialize(evaluation),
                classification=_text(evaluation.get("classification")) or "DISGRACE",
                hall={
                    "name": hall_name or _text(evaluation.get("hall_name")),
                    "entry": _serialize(self._hall_reference(hall_entry) or hall_entry or {}),
                },
                source=_text(packet.get("source")) or "codex",
            )
            self.runtime_law.ledger.record(
                "log_ingestion_classification",
                {
                    "trace_id": trace_id,
                    "packet_id": packet["packet_id"],
                    "candidate_id": candidate["candidate_id"],
                    "classification": evaluation["classification"],
                    "hall_name": hall_name or evaluation["hall_name"],
                },
                require_success=True,
            )
            outcomes.append(
                {
                    "trace_id": trace_id,
                    "candidate_id": candidate["candidate_id"],
                    "candidate": _serialize(candidate),
                    "evaluation": _serialize(evaluation),
                    "classification": evaluation["classification"],
                    "hall_name": hall_name or evaluation["hall_name"],
                    "hall_entry": _serialize(self._hall_reference(hall_entry) or hall_entry),
                    "verified": bool(getattr(finalized, "verified", False)),
                    "disposition": getattr(finalized, "disposition", decision.disposition),
                    "reason": getattr(finalized, "reason", decision.reason),
                    "trace": trace_entry,
                }
            )

        counts = {"FAME": 0, "SHAME": 0, "DISGRACE": 0}
        for item in outcomes:
            label = _text(item.get("classification")) or "DISGRACE"
            counts[label] = counts.get(label, 0) + 1
        result = {
            "ok": True,
            "packet": sanitized_packet,
            "candidate_count": len(candidates),
            "results": outcomes,
            "counts": counts,
        }
        self._record_activity({**result, "kind": "codex_log_ingestion"})
        return result

    def _current_integrity(self, *, trigger_lockdown: bool) -> dict[str, Any]:
        snapshot = self.integrity.verify_or_initialize(reseal=False)
        if trigger_lockdown and not snapshot.get("ok", False):
            self.kill_switch.lockdown(
                reason="protected_component_tamper_detected",
                actor="integrity",
                diagnostics={"integrity": snapshot},
            )
        return snapshot

    def _harm_risk_detected(
        self,
        *,
        action: dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> bool:
        sources = [
            _text(action.get("purpose")),
            _text(action.get("target")),
            _text(action.get("code")),
            _text(action.get("patch")),
            " ".join(_text(item) for item in list(action.get("command") or [])),
        ]
        if payload:
            sources.extend(
                [
                    _text(payload.get("error")),
                    _text(payload.get("stderr")),
                    json.dumps(_serialize(payload), sort_keys=True),
                ]
            )
        lowered = " ".join(part.lower() for part in sources if part)
        if _truthy(action.get("unsafe")):
            return True
        harmful_terms = (
            "destroy",
            "delete everything",
            "disable safeguards",
            "conceal",
            "deceive",
            "reckless",
            "harm",
            "bypass law",
        )
        return any(term in lowered for term in harmful_terms)

    def _weights_for_action(self, action: dict[str, Any]) -> dict[str, float]:
        return {
            "safety": 1.0,
            "truth": 1.0,
            "operator_intent": 1.0,
            "identity_integrity": 1.0,
            "speed": 0.25,
            "autonomy": 0.2,
            "future_integrity": 0.9,
        }

    def _values_claimed_for_action(self, action: dict[str, Any]) -> list[str]:
        claimed = [
            "non_harm",
            "non_domination",
            "identity_consistency",
            "existence_gate",
            "mutation_integrity",
            "verification_requirement",
        ]
        if not self._is_repo_changed_action(action):
            return claimed
        return claimed + ["verification_requirement"]

    def _shield_context_for_action(
        self,
        *,
        action: dict[str, Any],
        integrity: dict[str, Any],
        law_results: list[dict[str, Any]],
        guardrails: list[dict[str, Any]],
        phase: str,
        proposed_output: dict[str, Any] | None = None,
        forge_eval: list[dict[str, Any]] | None = None,
    ) -> DecisionContext:
        output = dict(proposed_output or {})
        if not output:
            output = {
                "status": "pending_validation",
                "target": action["target"],
                "action_type": action["action_type"],
            }
        mutation_artifact = _text(action.get("patch")) or _text(action.get("code")) or "mutation_artifact_present"
        if (
            action["action_type"] in REPO_CHANGE_ACTION_TYPES
            or action["action_type"].startswith("patch_")
        ) and not output.get("mutation_patch"):
            output["mutation_patch"] = mutation_artifact
        output.setdefault("status", "pending_validation" if phase == "entry" else "completed")
        evidence: dict[str, Any] = {
            "trace": {
                "phase": phase,
                "blueprint": self._build_blueprint_trace(action),
            },
            "review": {
                "laws": law_results,
                "guardrails": guardrails,
                "forge_eval": list(forge_eval or []),
            },
            "validation": {
                "integrity_ok": bool(integrity.get("ok", False)),
                "protected_count": int(integrity.get("protected_count", 0) or 0),
            },
        }
        if proposed_output:
            if proposed_output.get("verification_artifacts") is not None:
                evidence["verification_artifacts"] = proposed_output.get("verification_artifacts")
            if proposed_output.get("logbook_entry") is not None:
                evidence["proof"] = {"logbook_entry": proposed_output.get("logbook_entry")}
        failed_laws = [
            _text(result.get("id"))
            for result in law_results
            if not bool(result.get("passed", False))
        ]
        metadata = {
            "law_violations": failed_laws,
            "identity_drift_detected": bool(_truthy(action.get("authority_expansion"))),
            "domination_risk": bool(
                _truthy(action.get("unauthorized"))
                or _truthy(action.get("unbounded"))
                or _truthy(action.get("authority_expansion"))
            ),
            "harm_risk": self._harm_risk_detected(action=action, payload=proposed_output),
            "future_collapse_risk": bool(
                _truthy(action.get("bypass_requested"))
                or _truthy(action.get("protected_mutation"))
            ),
            "1001_bypass_attempt": bool(_truthy(action.get("bypass_requested"))),
            "conflict_resolved": not bool(_truthy(action.get("uncertain"))),
            "explanation_missing": not bool(_text(action.get("purpose"))),
        }
        return DecisionContext(
            actor=_text(action.get("source")) or "aris",
            action_type=action["action_type"],
            input_payload={
                "request": action["purpose"],
                "target": action["target"],
                "action_type": action["action_type"],
            },
            proposed_output=output,
            interpreted_intent=action["purpose"],
            weights=self._weights_for_action(action),
            values_claimed=self._values_claimed_for_action(action),
            evidence=evidence,
            metadata=metadata,
            mutation=action["action_type"] in REPO_CHANGE_ACTION_TYPES
            or action["action_type"].startswith("patch_"),
            conflict_present=bool(_truthy(action.get("uncertain"))),
        )

    def _shield_payload(
        self,
        *,
        action: dict[str, Any],
        integrity: dict[str, Any],
        law_results: list[dict[str, Any]],
        guardrails: list[dict[str, Any]],
        phase: str,
        proposed_output: dict[str, Any] | None = None,
        forge_eval: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        evaluation = self.shield_of_truth.judge(
            self._shield_context_for_action(
                action=action,
                integrity=integrity,
                law_results=law_results,
                guardrails=guardrails,
                phase=phase,
                proposed_output=proposed_output,
                forge_eval=forge_eval,
            )
        )
        payload = evaluation.to_dict()
        payload["passed"] = evaluation.verdict == ShieldVerdict.PASS
        payload["requires_escalation"] = evaluation.verdict == ShieldVerdict.ESCALATE
        payload["quarantined"] = evaluation.verdict == ShieldVerdict.QUARANTINED
        payload["title"] = "Shield of Truth"
        payload["reason"] = (
            "; ".join(evaluation.explanation[:3])
            if evaluation.explanation
            else f"Shield verdict: {evaluation.verdict.value}"
        )
        return payload

    def _maybe_emit_mystic_signal(self, *, session_id: str) -> dict[str, Any] | None:
        if self.mystic is None:
            return None
        signal = self.mystic.observe_activity(session_id=session_id)
        if signal is not None:
            self._record_activity(
                {
                    "kind": "mystic_reminder",
                    "session_id": session_id,
                    "mystic_signal": signal,
                    "disposition": "observed",
                }
            )
        return signal

    def _repo_relative_target(self, target: str) -> str:
        normalized = _text(target).replace("\\", "/")
        if not normalized:
            return ""
        candidate = Path(normalized)
        if not candidate.is_absolute():
            candidate = self.repo_root / candidate
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            resolved = candidate
        try:
            relative = resolved.relative_to(self.repo_root)
        except ValueError:
            relative = None
        if relative is not None:
            return str(relative).replace("\\", "/")
        return normalized

    def _is_repo_changed_action(self, action: dict[str, Any]) -> bool:
        if _truthy(action.get("repo_changed")):
            return True
        action_type = _text(action.get("action_type"))
        if action_type not in REPO_CHANGE_ACTION_TYPES:
            return False
        target = self._repo_relative_target(_text(action.get("target")))
        return any(target == hint or target.startswith(hint) for hint in REPO_TARGET_HINTS)

    def _has_1001_pass(self, decision: GovernanceDecision) -> bool:
        return any(
            _text(result.get("id")) == "1001" and bool(result.get("passed"))
            for result in decision.law_results
        )

    def _has_verification_artifacts(self, payload: dict[str, Any]) -> bool:
        artifacts = payload.get("verification_artifacts")
        if isinstance(artifacts, list):
            return any(bool(_text(item)) if not isinstance(item, dict) else bool(item) for item in artifacts)
        if isinstance(artifacts, dict):
            return bool(artifacts)
        return bool(_text(artifacts))

    def _logbook_entry_matches_change(
        self,
        *,
        payload: dict[str, Any],
        decision: GovernanceDecision,
    ) -> bool:
        entry = payload.get("logbook_entry")
        if not isinstance(entry, dict):
            return False
        return (
            bool(entry.get("recorded"))
            and _text(entry.get("path")) == str(self.logbook.path)
            and _text(entry.get("action_id")) == decision.action_id
            and _text(entry.get("fingerprint")) == decision.fingerprint
        )

    def _touches_protected_runtime(self, *, target: str, patch: str, command: list[str]) -> bool:
        normalized_target = target.replace("\\", "/").strip()
        protected_hits = any(
            normalized_target.startswith(relative)
            for relative in PROTECTED_RUNTIME_RELATIVE_PATHS
        )
        if protected_hits:
            return True
        lowered_patch = patch.replace("\\", "/")
        for relative in PROTECTED_RUNTIME_RELATIVE_PATHS:
            if relative in lowered_patch:
                return True
        command_text = " ".join(command).replace("\\", "/")
        return any(relative in command_text for relative in PROTECTED_RUNTIME_RELATIVE_PATHS)

    def _normalize_action(self, action: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(action)
        normalized["action_id"] = _text(action.get("action_id")) or f"aris_{uuid.uuid4().hex[:12]}"
        normalized["action_type"] = _text(action.get("action_type")) or "unknown"
        normalized["purpose"] = _text(action.get("purpose")) or "Undeclared ARIS action"
        normalized["target"] = _text(action.get("target"))
        normalized["source"] = _text(action.get("source")) or "api"
        normalized["session_id"] = _text(action.get("session_id")) or "system"
        normalized["operator_decision"] = _text(action.get("operator_decision")) or "approved"
        normalized["command"] = [
            _text(item) for item in list(action.get("command") or []) if _text(item)
        ]
        normalized["code"] = str(action.get("code") or "")
        normalized["patch"] = str(action.get("patch") or "")
        normalized["claimed_identity"] = _text(action.get("claimed_identity"))
        normalized["legitimacy_token"] = _text(action.get("legitimacy_token"))
        normalized["authorized"] = True
        normalized["observed"] = True
        normalized["bounded"] = True
        normalized["uncertain"] = False
        normalized["unsafe"] = False
        normalized["failed"] = False
        normalized["flagged"] = False
        normalized["unverified"] = False
        normalized["unauthorized"] = False
        normalized["unbounded"] = False
        normalized["unobservable"] = False
        normalized["out_of_contract"] = False
        normalized["bypass_requested"] = action.get("bypass_requested", False)
        normalized["authority_expansion"] = action.get("authority_expansion", False)
        normalized["allow_new_file"] = action.get("allow_new_file", False)
        normalized["repo_changed"] = self._is_repo_changed_action(normalized)
        normalized["protected_mutation"] = self._touches_protected_runtime(
            target=normalized["target"],
            patch=normalized["patch"],
            command=normalized["command"],
        )
        return normalized

    def _build_blueprint_trace(self, action: dict[str, Any]) -> dict[str, Any]:
        risk_flags = [
            label
            for label in (
                "risky_path" if action["action_type"] in RISKY_ACTION_TYPES else "",
                "protected_mutation" if action["protected_mutation"] else "",
                "authority_expansion" if _truthy(action.get("authority_expansion")) else "",
            )
            if label
        ]
        trace = self.reasoner.build_trace(
            action_type=action["action_type"],
            purpose=action["purpose"],
            session_id=action["session_id"],
            target=action["target"],
            risk_flags=risk_flags,
            requires_forge_eval=action["action_type"] in RISKY_ACTION_TYPES,
            startup_blockers=list(self._startup["startup_blockers"]) if hasattr(self, "_startup") else [],
        )
        return trace.payload()

    def _evaluate_laws(self, action: dict[str, Any], *, integrity: dict[str, Any]) -> list[dict[str, Any]]:
        meta_checks = {
            "begins_under_law": bool(action.get("law_context_bound", False)),
            "non_bypassable_validation": not _truthy(action.get("bypass_requested")),
            "verification_path_bound": self.forge_eval is not None or action["action_type"] not in RISKY_ACTION_TYPES,
            "integrity_ok": bool(integrity.get("ok", False)),
            "root_law_loaded": bool(self.runtime_law.bootstrap_state.ok),
        }
        foundation_checks = {
            "safe_adaptation_only": not _truthy(action.get("unsafe")),
            "reject_failed_code": not _truthy(action.get("failed")),
            "mandatory_containment_available": True,
        }
        return [
            {
                "id": META_LAW_1001["id"],
                "title": META_LAW_1001["title"],
                "passed": all(meta_checks.values()),
                "checks": meta_checks,
                "reason": "ARIS 1001 gate checked." if all(meta_checks.values()) else "ARIS 1001 gate failed.",
            },
            {
                "id": FOUNDATION_LAW["id"],
                "title": FOUNDATION_LAW["title"],
                "passed": all(foundation_checks.values()),
                "checks": foundation_checks,
                "reason": (
                    "Foundation law checks passed."
                    if all(foundation_checks.values())
                    else "Foundation law checks failed."
                ),
            },
        ]

    def _evaluate_guardrails(self, action: dict[str, Any]) -> list[dict[str, Any]]:
        declared_purpose = bool(action["purpose"])
        safe_adaptation = not any(
            _truthy(action.get(name))
            for name in (
                "unsafe",
                "failed",
                "flagged",
                "unverified",
                "protected_mutation",
                "out_of_contract",
            )
        )
        bounded_authority = not any(
            _truthy(action.get(name))
            for name in ("unauthorized", "unbounded", "authority_expansion")
        ) and _truthy(action.get("authorized", True)) and _truthy(action.get("bounded", True))
        observability = _truthy(action.get("observed", True)) and not _truthy(
            action.get("unobservable")
        )
        risky = self._is_risky(action, law_results=[], guardrails=[])
        verified_escalation = not risky or self.forge_eval is not None
        values = {
            "declared_purpose": declared_purpose,
            "safe_adaptation": safe_adaptation,
            "bounded_authority": bounded_authority,
            "observability": observability,
            "verified_escalation": verified_escalation,
        }
        results: list[dict[str, Any]] = []
        for guardrail in GUARDRAILS:
            passed = bool(values[guardrail["id"]])
            results.append(
                {
                    "id": guardrail["id"],
                    "title": guardrail["title"],
                    "summary": guardrail["summary"],
                    "passed": passed,
                    "reason": (
                        f"{guardrail['title']} satisfied."
                        if passed
                        else f"{guardrail['title']} failed."
                    ),
                }
            )
        return results

    def _is_risky(
        self,
        action: dict[str, Any],
        *,
        law_results: list[dict[str, Any]],
        guardrails: list[dict[str, Any]],
    ) -> bool:
        if action["action_type"] in RISKY_ACTION_TYPES:
            return True
        if any(not bool(item.get("passed", False)) for item in law_results + guardrails):
            return True
        return any(
            _truthy(action.get(name))
            for name in (
                "unsafe",
                "uncertain",
                "failed",
                "flagged",
                "unverified",
                "unauthorized",
                "unbounded",
                "unobservable",
                "out_of_contract",
                "protected_mutation",
                "authority_expansion",
            )
        )

    def _dangerous_command_terms(self) -> list[str]:
        return [
            "rm -rf",
            "git reset --hard",
            "git checkout --",
            "del /f",
            "format ",
            "powershell",
            "pwsh",
            "bash",
            "cmd /c",
        ]

    def _run_forge_eval(self, action: dict[str, Any]) -> list[dict[str, Any]]:
        if self.forge_eval is None:
            return [
                {
                    "mode": "missing",
                    "passed": False,
                    "status_code": 503,
                    "reason": "Forge Eval is not connected.",
                    "raw": {},
                }
            ]

        results: list[dict[str, Any]] = []
        payload_text = action["patch"] or action["code"] or " ".join(action["command"])
        normalized_patch = action["patch"]
        if normalized_patch and "+++ b/" not in normalized_patch and action["target"]:
            target = action["target"].replace("\\", "/").strip()
            normalized_patch = f"--- a/{target}\n+++ b/{target}\n{normalized_patch.lstrip()}"

        def _failed_io_reason(base_reason: str, checks: list[dict[str, Any]]) -> str:
            failed_needles = [
                _text(item.get("needle"))
                for item in checks
                if not bool(item.get("passed")) and _text(item.get("needle"))
            ]
            if not failed_needles:
                return base_reason
            if len(failed_needles) == 1:
                return f"{base_reason} `{failed_needles[0]}` is not allowed."
            return f"{base_reason} Not allowed: {', '.join(f'`{needle}`' for needle in failed_needles)}."

        if action["patch"]:
            request_payload = {
                "task_id": action["action_id"],
                "mode": "repo_patch",
                "payload": {
                    "patch": normalized_patch,
                    "repo": str(self.repo_root),
                    "lineage": _text(action.get("lineage")),
                    "target": action["target"],
                    "diff_present": bool(action["patch"]),
                    "test_result": "not_run",
                    "config": {
                        "expected_files": [action["target"]] if action["target"] else [],
                    },
                },
            }
            response, status_code = self.forge_eval.evaluate(request_payload)
            raw = response.model_dump(exclude_none=True)
            details = raw.get("result", {}).get("details", {}) if status_code == 200 else {}
            touched_files = {
                _text(item).replace("\\", "/")
                for item in list(details.get("touched_files") or [])
                if _text(item)
            }
            expected_files = {
                _text(item).replace("\\", "/")
                for item in list(details.get("expected_files") or [])
                if _text(item)
            }
            passed = status_code == 200 and (
                not expected_files or bool(touched_files & expected_files)
            )
            results.append(
                {
                    "mode": "repo_patch",
                    "passed": passed,
                    "status_code": status_code,
                    "reason": (
                        "Forge Eval confirmed the patch scope."
                        if passed
                        else "Forge Eval rejected the patch scope."
                    ),
                    "raw": raw,
                }
            )
        if action["command"]:
            request_payload = {
                "task_id": action["action_id"],
                "mode": "io_tests",
                "payload": {
                    "program": " ".join(action["command"]),
                    "lineage": _text(action.get("lineage")),
                    "target": action["target"],
                    "diff_present": False,
                    "test_result": "not_run",
                    "config": {
                        "must_not_contain": self._dangerous_command_terms(),
                    },
                },
            }
            response, status_code = self.forge_eval.evaluate(request_payload)
            raw = response.model_dump(exclude_none=True)
            checks = list(raw.get("result", {}).get("details", {}).get("checks", []))
            passed = status_code == 200 and all(bool(item.get("passed")) for item in checks)
            results.append(
                {
                    "mode": "io_tests",
                    "passed": passed,
                    "status_code": status_code,
                    "reason": (
                        "Forge Eval cleared the command request."
                        if passed
                        else _failed_io_reason("Forge Eval rejected the command request.", checks)
                    ),
                    "raw": raw,
                }
            )
        if action["code"]:
            request_payload = {
                "task_id": action["action_id"],
                "mode": "io_tests",
                "payload": {
                    "program": action["code"],
                    "lineage": _text(action.get("lineage")),
                    "target": action["target"],
                    "diff_present": False,
                    "test_result": "not_run",
                    "config": {
                        "must_not_contain": [
                            "subprocess",
                            "socket",
                            "os.system",
                            "shutil.rmtree",
                            "eval(",
                            "exec(",
                        ],
                    },
                },
            }
            response, status_code = self.forge_eval.evaluate(request_payload)
            raw = response.model_dump(exclude_none=True)
            checks = list(raw.get("result", {}).get("details", {}).get("checks", []))
            passed = status_code == 200 and all(bool(item.get("passed")) for item in checks)
            results.append(
                {
                    "mode": "io_tests",
                    "passed": passed,
                    "status_code": status_code,
                    "reason": (
                        "Forge Eval cleared the Python execution request."
                        if passed
                        else _failed_io_reason("Forge Eval rejected the Python execution request.", checks)
                    ),
                    "raw": raw,
                }
            )
        if not results and payload_text:
            request_payload = {
                "task_id": action["action_id"],
                "mode": "llm_rubric",
                "payload": {
                    "program": payload_text,
                    "lineage": _text(action.get("lineage")),
                    "target": action["target"],
                    "diff_present": bool(action["patch"]),
                    "test_result": "not_run",
                    "config": {
                        "criteria": [
                            {
                                "label": "purpose-visible",
                                "required_terms": [action["purpose"].lower()] if action["purpose"] else [],
                            }
                        ]
                    },
                },
            }
            response, status_code = self.forge_eval.evaluate(request_payload)
            raw = response.model_dump(exclude_none=True)
            criteria = list(raw.get("result", {}).get("details", {}).get("criteria", []))
            passed = status_code == 200 and all(
                float(item.get("score", 0.0)) >= 1.0 for item in criteria
            )
            results.append(
                {
                    "mode": "llm_rubric",
                    "passed": passed,
                    "status_code": status_code,
                    "reason": (
                        "Forge Eval completed rubric verification."
                        if passed
                        else "Forge Eval rubric verification failed."
                    ),
                    "raw": raw,
                }
            )
        if not results:
            results.append(
                {
                    "mode": "noop",
                    "passed": False,
                    "status_code": 400,
                    "reason": "No evaluable Forge Eval artifact was provided.",
                    "raw": {},
                }
            )
        return results

    def _discard(
        self,
        *,
        action: dict[str, Any],
        fingerprint: str,
        reason: str,
        law_results: list[dict[str, Any]],
        guardrails: list[dict[str, Any]],
        forge_eval: list[dict[str, Any]],
        operator_decision: str,
        notes: str = "",
        lineage_key: str = "",
        re_evaluation_of: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.hall_of_discard.discard(
            fingerprint=fingerprint,
            lineage_key=lineage_key,
            action={
                "action_id": action["action_id"],
                "action_type": action["action_type"],
                "purpose": action["purpose"],
                "target": action["target"],
                "source": action["source"],
                "session_id": action["session_id"],
                "command": list(action["command"]),
            },
            reason=reason,
            law_results=law_results,
            guardrails=guardrails,
            operator_decision=operator_decision,
            forge_eval=forge_eval,
            source=action["source"],
            notes=notes,
            re_evaluation_of=re_evaluation_of,
        )

    def _shame(
        self,
        *,
        action: dict[str, Any],
        fingerprint: str,
        reason: str,
        law_results: list[dict[str, Any]],
        guardrails: list[dict[str, Any]],
        forge_eval: list[dict[str, Any]],
        operator_decision: str,
        notes: str = "",
        metadata: dict[str, Any] | None = None,
        lineage_key: str = "",
        re_evaluation_of: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.hall_of_shame.shame(
            fingerprint=fingerprint,
            lineage_key=lineage_key,
            action={
                "action_id": action["action_id"],
                "action_type": action["action_type"],
                "purpose": action["purpose"],
                "target": action["target"],
                "source": action["source"],
                "session_id": action["session_id"],
                "command": list(action["command"]),
            },
            reason=reason,
            law_results=law_results,
            guardrails=guardrails,
            operator_decision=operator_decision,
            forge_eval=forge_eval,
            source=action["source"],
            notes=notes,
            metadata=metadata,
            re_evaluation_of=re_evaluation_of,
        )

    def _fame(
        self,
        *,
        action: dict[str, Any],
        fingerprint: str,
        reason: str,
        law_results: list[dict[str, Any]],
        guardrails: list[dict[str, Any]],
        forge_eval: list[dict[str, Any]],
        operator_decision: str,
        notes: str = "",
        metadata: dict[str, Any] | None = None,
        lineage_key: str = "",
        re_evaluation_of: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.hall_of_fame.celebrate(
            fingerprint=fingerprint,
            lineage_key=lineage_key,
            action={
                "action_id": action["action_id"],
                "action_type": action["action_type"],
                "purpose": action["purpose"],
                "target": action["target"],
                "source": action["source"],
                "session_id": action["session_id"],
                "command": list(action["command"]),
            },
            reason=reason,
            law_results=law_results,
            guardrails=guardrails,
            operator_decision=operator_decision,
            forge_eval=forge_eval,
            source=action["source"],
            notes=notes,
            containment_status="verified",
            metadata=metadata,
            re_evaluation_of=re_evaluation_of,
        )

    def _fingerprint_for_action(
        self,
        *,
        action_type: str,
        purpose: str,
        target: str,
        patch: str,
        command: list[str],
        code: str,
        metadata: dict[str, Any],
    ) -> str:
        return self.hall_of_discard.fingerprint_for(
            action_type=action_type,
            purpose=purpose,
            target=target,
            patch=patch,
            command=command,
            code=code,
            metadata=metadata,
        )

    def _lineage_for_action(
        self,
        *,
        action_type: str,
        purpose: str,
        target: str,
        metadata: dict[str, Any],
    ) -> str:
        return self.hall_of_discard.fingerprint_for(
            action_type=action_type,
            purpose=purpose,
            target=target,
            patch="",
            command=[],
            code="",
            metadata={
                "source": _text(metadata.get("source")),
                "session_id": _text(metadata.get("session_id")),
                "lineage": "aris-governed-item",
            },
        )

    def _hall_reference(self, entry: dict[str, Any] | None) -> dict[str, Any] | None:
        if not entry:
            return None
        return {
            "hall": _text(entry.get("hall")),
            "entry_id": _text(entry.get("id")),
            "fingerprint": _text(entry.get("fingerprint")),
            "lineage_key": _text(entry.get("lineage_key")),
            "created_at": _text(entry.get("created_at")),
        }

    def _find_latest_lineage_entry(self, lineage_key: str) -> dict[str, Any] | None:
        normalized = _text(lineage_key)
        if not normalized:
            return None
        candidates = [
            hall.find_latest_by_lineage(normalized)
            for hall in (self.hall_of_discard, self.hall_of_shame, self.hall_of_fame)
        ]
        matches = [entry for entry in candidates if entry]
        if not matches:
            return None
        return max(matches, key=lambda entry: _text(entry.get("created_at")))

    def _find_reentry_blocker(self, fingerprint: str) -> dict[str, Any] | None:
        return self.hall_of_discard.find_reentry_blocker(
            fingerprint
        ) or self.hall_of_shame.find_reentry_blocker(fingerprint)

    def _failure_hall_name(
        self,
        *,
        action: dict[str, Any],
        reason: str,
        forge_eval: list[dict[str, Any]],
        failure_kind: str | None = None,
    ) -> str:
        if failure_kind == "success":
            return "hall_of_fame"
        if failure_kind == "escalation":
            return "hall_of_discard"
        if failure_kind == "correctness":
            return "hall_of_shame"
        lowered_reason = reason.lower()
        if any(not bool(item.get("passed", False)) for item in forge_eval):
            return "hall_of_discard"
        if any(
            marker in lowered_reason
            for marker in (
                "forge eval",
                "verification",
                "verified",
                "escalation",
                "bypass",
                "unverified",
            )
        ):
            return "hall_of_discard"
        if action["operator_decision"] == "approved" and action["action_type"] in RISKY_ACTION_TYPES:
            return "hall_of_discard"
        return "hall_of_shame"

    def _record_failure_hall(
        self,
        *,
        action: dict[str, Any],
        fingerprint: str,
        reason: str,
        law_results: list[dict[str, Any]],
        guardrails: list[dict[str, Any]],
        forge_eval: list[dict[str, Any]],
        operator_decision: str,
        notes: str = "",
        failure_kind: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        lineage_key = _text(action.get("lineage_key"))
        re_evaluation_of = self._hall_reference(action.get("previous_lineage_entry"))
        hall_name = self._failure_hall_name(
            action=action,
            reason=reason,
            forge_eval=forge_eval,
            failure_kind=failure_kind,
        )
        if hall_name == "hall_of_discard":
            return hall_name, self._discard(
                action=action,
                fingerprint=fingerprint,
                reason=reason,
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=forge_eval,
                operator_decision=operator_decision,
                notes=notes,
                lineage_key=lineage_key,
                re_evaluation_of=re_evaluation_of,
            )
        return hall_name, self._shame(
            action=action,
            fingerprint=fingerprint,
            reason=reason,
            law_results=law_results,
            guardrails=guardrails,
            forge_eval=forge_eval,
            operator_decision=operator_decision,
            notes=notes,
            metadata=metadata,
            lineage_key=lineage_key,
            re_evaluation_of=re_evaluation_of,
        )

    def review_action(self, action: dict[str, Any]) -> GovernanceDecision:
        normalized = self._normalize_action(action)
        mystic_signal = self._maybe_emit_mystic_signal(session_id=normalized["session_id"])
        kill_snapshot = self.kill_switch.snapshot()
        if self.kill_switch.blocks(action_type=normalized["action_type"]):
            blueprint_trace = self._build_blueprint_trace(normalized)
            decision = GovernanceDecision(
                action_id=normalized["action_id"],
                action_type=normalized["action_type"],
                purpose=normalized["purpose"],
                target=normalized["target"],
                source=normalized["source"],
                session_id=normalized["session_id"],
                operator_decision=normalized["operator_decision"],
                risky=True,
                requires_forge_eval=True,
                allowed=False,
                verified=False,
                disposition="blocked",
                reason=_text(kill_snapshot.get("summary")) or "ARIS kill switch is active.",
                fingerprint="",
                blueprint_trace=blueprint_trace,
                law_results=[],
                guardrails=[],
                forge_eval=[],
                integrity=self._startup["integrity"],
                reentry_blocker=None,
                kill_switch=kill_snapshot,
                action=normalized,
                created_at=_utc_now(),
                mystic_signal=mystic_signal,
            )
            self._record_activity({**decision.payload(), "kind": "governance_review"})
            return decision

        integrity = self._current_integrity(trigger_lockdown=True)
        preflight = self.operator_router.preflight(
            action=normalized,
            actor=normalized["source"],
            route_name=normalized["action_type"],
            repo_changed=normalized["repo_changed"],
            protected_target=normalized["protected_mutation"],
        )
        normalized.update(preflight.derived_flags)
        blueprint_trace = self._build_blueprint_trace(normalized)
        law_results = self._evaluate_laws(normalized, integrity=integrity)
        guardrails = self._evaluate_guardrails(normalized)
        shield = self._shield_payload(
            action=normalized,
            integrity=integrity,
            law_results=law_results,
            guardrails=guardrails,
            phase="entry",
        )
        if not preflight.allowed:
            override = preflight.override or {}
            if preflight.override is not None:
                if preflight.override.severity == "critical" or preflight.override.kind == "law_bypass_attempt":
                    kill_snapshot = self.kill_switch.hard_kill(
                        reason=preflight.override.kind,
                        actor="runtime_law",
                        diagnostics={"law_preflight": preflight.payload()},
                    )
                elif preflight.override.quarantine:
                    kill_snapshot = self.kill_switch.lockdown(
                        reason=preflight.override.kind,
                        actor="runtime_law",
                        diagnostics={"law_preflight": preflight.payload()},
                    )
            hall_name, hall_entry = self._record_failure_hall(
                action=normalized,
                fingerprint=self._fingerprint_for_action(
                    action_type=normalized["action_type"],
                    purpose=normalized["purpose"],
                    target=normalized["target"],
                    patch=normalized["patch"],
                    command=normalized["command"],
                    code=normalized["code"],
                    metadata={"source": normalized["source"], "session_id": normalized["session_id"]},
                ),
                reason=preflight.reason,
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=[],
                operator_decision=normalized["operator_decision"],
                failure_kind="escalation" if override else "correctness",
                metadata={"law_preflight": preflight.payload()},
            )
            decision = GovernanceDecision(
                action_id=normalized["action_id"],
                action_type=normalized["action_type"],
                purpose=normalized["purpose"],
                target=normalized["target"],
                source=normalized["source"],
                session_id=normalized["session_id"],
                operator_decision=normalized["operator_decision"],
                risky=True,
                requires_forge_eval=normalized["action_type"] in RISKY_ACTION_TYPES,
                allowed=False,
                verified=False,
                disposition="discarded",
                reason=preflight.reason,
                fingerprint=self._fingerprint_for_action(
                    action_type=normalized["action_type"],
                    purpose=normalized["purpose"],
                    target=normalized["target"],
                    patch=normalized["patch"],
                    command=normalized["command"],
                    code=normalized["code"],
                    metadata={"source": normalized["source"], "session_id": normalized["session_id"]},
                ),
                blueprint_trace=blueprint_trace,
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=[],
                integrity=integrity,
                reentry_blocker=None,
                kill_switch=kill_snapshot,
                action=normalized,
                created_at=_utc_now(),
                discard_entry=hall_entry if hall_name == "hall_of_discard" else None,
                hall_name=hall_name,
                hall_entry=hall_entry,
                shield=shield,
                mystic_signal=mystic_signal,
            )
            self._record_activity({**decision.payload(), "kind": "governance_review"})
            return decision
        risky = self._is_risky(normalized, law_results=law_results, guardrails=guardrails) or bool(
            shield.get("requires_escalation") or shield.get("quarantined") or not shield.get("passed", False)
        )
        requires_forge_eval = risky and normalized["operator_decision"] == "approved"
        fingerprint = self._fingerprint_for_action(
            action_type=normalized["action_type"],
            purpose=normalized["purpose"],
            target=normalized["target"],
            patch=normalized["patch"],
            command=normalized["command"],
            code=normalized["code"],
            metadata={
                "source": normalized["source"],
                "session_id": normalized["session_id"],
            },
        )
        normalized["lineage_key"] = self._lineage_for_action(
            action_type=normalized["action_type"],
            purpose=normalized["purpose"],
            target=normalized["target"],
            metadata={
                "source": normalized["source"],
                "session_id": normalized["session_id"],
            },
        )
        normalized["previous_lineage_entry"] = self._find_latest_lineage_entry(
            normalized["lineage_key"]
        )
        reentry_blocker = self._find_reentry_blocker(fingerprint)

        if _truthy(normalized.get("bypass_requested")):
            kill_snapshot = self.kill_switch.hard_kill(
                reason="forge_eval_bypass_attempt",
                actor="governance",
                diagnostics={"action_id": normalized["action_id"], "action_type": normalized["action_type"]},
            )
            hall_name, hall_entry = self._record_failure_hall(
                action=normalized,
                fingerprint=fingerprint,
                reason="Forge Eval bypass attempt detected.",
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=[],
                operator_decision=normalized["operator_decision"],
                failure_kind="escalation",
            )
            decision = GovernanceDecision(
                action_id=normalized["action_id"],
                action_type=normalized["action_type"],
                purpose=normalized["purpose"],
                target=normalized["target"],
                source=normalized["source"],
                session_id=normalized["session_id"],
                operator_decision=normalized["operator_decision"],
                risky=True,
                requires_forge_eval=True,
                allowed=False,
                verified=False,
                disposition="discarded",
                reason="Forge Eval bypass attempt detected.",
                fingerprint=fingerprint,
                blueprint_trace=blueprint_trace,
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=[],
                integrity=integrity,
                reentry_blocker=reentry_blocker,
                kill_switch=kill_snapshot,
                action=normalized,
                created_at=_utc_now(),
                discard_entry=hall_entry if hall_name == "hall_of_discard" else None,
                hall_name=hall_name,
                hall_entry=hall_entry,
                shield=shield,
                mystic_signal=mystic_signal,
            )
            self._record_activity({**decision.payload(), "kind": "governance_review"})
            return decision

        if bool(shield.get("quarantined")):
            kill_snapshot = self.kill_switch.lockdown(
                reason="shield_of_truth_quarantine",
                actor="shield_of_truth",
                diagnostics={
                    "action_id": normalized["action_id"],
                    "action_type": normalized["action_type"],
                    "shield": shield,
                },
            )
            hall_name, hall_entry = self._record_failure_hall(
                action=normalized,
                fingerprint=fingerprint,
                reason="Shield of Truth quarantined the action.",
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=[],
                operator_decision=normalized["operator_decision"],
                failure_kind="escalation",
                metadata={"shield": shield},
            )
            decision = GovernanceDecision(
                action_id=normalized["action_id"],
                action_type=normalized["action_type"],
                purpose=normalized["purpose"],
                target=normalized["target"],
                source=normalized["source"],
                session_id=normalized["session_id"],
                operator_decision=normalized["operator_decision"],
                risky=True,
                requires_forge_eval=True,
                allowed=False,
                verified=False,
                disposition="discarded",
                reason="Shield of Truth quarantined the action.",
                fingerprint=fingerprint,
                blueprint_trace=blueprint_trace,
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=[],
                integrity=integrity,
                reentry_blocker=reentry_blocker,
                kill_switch=kill_snapshot,
                action=normalized,
                created_at=_utc_now(),
                discard_entry=hall_entry if hall_name == "hall_of_discard" else None,
                hall_name=hall_name,
                hall_entry=hall_entry,
                shield=shield,
                mystic_signal=mystic_signal,
            )
            self._record_activity({**decision.payload(), "kind": "governance_review"})
            return decision

        if normalized["protected_mutation"] or _truthy(normalized.get("authority_expansion")):
            kill_snapshot = self.kill_switch.lockdown(
                reason="protected_component_mutation_attempt",
                actor="governance",
                diagnostics={
                    "action_id": normalized["action_id"],
                    "action_type": normalized["action_type"],
                    "target": normalized["target"],
                },
            )
            hall_name, hall_entry = self._record_failure_hall(
                action=normalized,
                fingerprint=fingerprint,
                reason="Mutation touching protected law or authority paths was blocked.",
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=[],
                operator_decision=normalized["operator_decision"],
                failure_kind="correctness",
            )
            decision = GovernanceDecision(
                action_id=normalized["action_id"],
                action_type=normalized["action_type"],
                purpose=normalized["purpose"],
                target=normalized["target"],
                source=normalized["source"],
                session_id=normalized["session_id"],
                operator_decision=normalized["operator_decision"],
                risky=True,
                requires_forge_eval=True,
                allowed=False,
                verified=False,
                disposition="discarded",
                reason="Protected component mutation attempt blocked.",
                fingerprint=fingerprint,
                blueprint_trace=blueprint_trace,
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=[],
                integrity=integrity,
                reentry_blocker=reentry_blocker,
                kill_switch=kill_snapshot,
                action=normalized,
                created_at=_utc_now(),
                discard_entry=hall_entry if hall_name == "hall_of_discard" else None,
                hall_name=hall_name,
                hall_entry=hall_entry,
                shield=shield,
                mystic_signal=mystic_signal,
            )
            self._record_activity({**decision.payload(), "kind": "governance_review"})
            return decision

        if not _truthy(normalized.get("observed", True)) or _truthy(normalized.get("unobservable")):
            kill_snapshot = self.kill_switch.lockdown(
                reason="hidden_or_unobservable_critical_action",
                actor="governance",
                diagnostics={"action_id": normalized["action_id"], "action_type": normalized["action_type"]},
            )
            hall_name, hall_entry = self._record_failure_hall(
                action=normalized,
                fingerprint=fingerprint,
                reason="Hidden or unobservable critical action was blocked.",
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=[],
                operator_decision=normalized["operator_decision"],
                failure_kind="correctness",
            )
            decision = GovernanceDecision(
                action_id=normalized["action_id"],
                action_type=normalized["action_type"],
                purpose=normalized["purpose"],
                target=normalized["target"],
                source=normalized["source"],
                session_id=normalized["session_id"],
                operator_decision=normalized["operator_decision"],
                risky=True,
                requires_forge_eval=True,
                allowed=False,
                verified=False,
                disposition="discarded",
                reason="Hidden or unobservable critical action was blocked.",
                fingerprint=fingerprint,
                blueprint_trace=blueprint_trace,
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=[],
                integrity=integrity,
                reentry_blocker=reentry_blocker,
                kill_switch=kill_snapshot,
                action=normalized,
                created_at=_utc_now(),
                discard_entry=hall_entry if hall_name == "hall_of_discard" else None,
                hall_name=hall_name,
                hall_entry=hall_entry,
                shield=shield,
                mystic_signal=mystic_signal,
            )
            self._record_activity({**decision.payload(), "kind": "governance_review"})
            return decision

        if reentry_blocker is not None:
            decision = GovernanceDecision(
                action_id=normalized["action_id"],
                action_type=normalized["action_type"],
                purpose=normalized["purpose"],
                target=normalized["target"],
                source=normalized["source"],
                session_id=normalized["session_id"],
                operator_decision=normalized["operator_decision"],
                risky=risky,
                requires_forge_eval=requires_forge_eval,
                allowed=False,
                verified=False,
                disposition="blocked",
                reason=(
                    "A prior hall entry blocked unchanged re-entry. Redesign and re-evaluate "
                    "under current law before retrying this action."
                ),
                fingerprint=fingerprint,
                blueprint_trace=blueprint_trace,
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=[],
                integrity=integrity,
                reentry_blocker=reentry_blocker,
                kill_switch=self.kill_switch.snapshot(),
                action=normalized,
                created_at=_utc_now(),
                shield=shield,
                mystic_signal=mystic_signal,
            )
            self._record_activity({**decision.payload(), "kind": "governance_review"})
            return decision

        forge_eval_results = self._run_forge_eval(normalized) if requires_forge_eval else []
        shield_passed = bool(shield.get("passed", False)) or (
            bool(shield.get("requires_escalation"))
            and requires_forge_eval
            and all(item["passed"] for item in forge_eval_results)
        )
        allowed = (
            all(item["passed"] for item in law_results)
            and all(item["passed"] for item in guardrails)
            and shield_passed
            and (not requires_forge_eval or all(item["passed"] for item in forge_eval_results))
        )
        if allowed:
            reason = "Action passed ARIS law review and verification."
        else:
            failed_forge_eval = next(
                (item for item in forge_eval_results if not item["passed"]),
                None,
            )
            failed_guardrail = next(
                (item for item in guardrails if not item["passed"]),
                None,
            )
            failed_law = next((item for item in law_results if not item["passed"]), None)
            if failed_forge_eval is not None:
                reason = _text(failed_forge_eval.get("reason")) or "Action blocked by ARIS law review."
            elif failed_guardrail is not None:
                reason = _text(failed_guardrail.get("reason")) or "Action blocked by ARIS law review."
            elif failed_law is not None:
                reason = _text(failed_law.get("reason")) or "Action blocked by ARIS law review."
            else:
                reason = "Action blocked by ARIS law review."
        discard_entry = None
        hall_name = None
        hall_entry = None
        if not allowed:
            hall_name, hall_entry = self._record_failure_hall(
                action=normalized,
                fingerprint=fingerprint,
                reason=reason,
                law_results=law_results,
                guardrails=guardrails,
                forge_eval=forge_eval_results,
                operator_decision=normalized["operator_decision"],
            )
            discard_entry = hall_entry if hall_name == "hall_of_discard" else None
            if self._recent_unsafe_escalations(limit=10) >= 2:
                self.kill_switch.hard_kill(
                    reason="repeated_unsafe_escalation_attempts",
                    actor="governance",
                    diagnostics={"session_id": normalized["session_id"]},
                )
        decision = GovernanceDecision(
            action_id=normalized["action_id"],
            action_type=normalized["action_type"],
            purpose=normalized["purpose"],
            target=normalized["target"],
            source=normalized["source"],
            session_id=normalized["session_id"],
            operator_decision=normalized["operator_decision"],
            risky=risky,
            requires_forge_eval=requires_forge_eval,
            allowed=allowed,
            verified=False,
            disposition="approved" if allowed else "discarded",
            reason=reason,
            fingerprint=fingerprint,
            blueprint_trace=blueprint_trace,
            law_results=law_results,
            guardrails=guardrails,
            forge_eval=forge_eval_results,
            integrity=integrity,
            reentry_blocker=reentry_blocker,
            kill_switch=self.kill_switch.snapshot(),
            action=normalized,
            created_at=_utc_now(),
            discard_entry=discard_entry,
            hall_name=hall_name,
            hall_entry=hall_entry,
            shield=shield,
            mystic_signal=mystic_signal,
        )
        self._record_activity({**decision.payload(), "kind": "governance_review"})
        return decision

    def finalize_action(
        self,
        decision: GovernanceDecision,
        *,
        result: dict[str, Any] | None = None,
    ) -> GovernanceDecision:
        payload = dict(result or {})
        action = decision.action
        active_kill = self.kill_switch.snapshot()
        if decision.allowed and self.kill_switch.blocks(action_type=decision.action_type):
            hall_name, hall_entry = self._record_failure_hall(
                action=action,
                fingerprint=decision.fingerprint,
                reason=_text(active_kill.get("summary")) or "ARIS kill switch is active.",
                law_results=decision.law_results,
                guardrails=decision.guardrails,
                forge_eval=decision.forge_eval,
                operator_decision=decision.operator_decision,
                notes="Execution was halted after approval because the kill switch engaged.",
                failure_kind="escalation",
            )
            finalized = GovernanceDecision(
                **{
                    **self._decision_values(decision),
                    "allowed": False,
                    "verified": False,
                    "disposition": "discarded",
                    "reason": _text(active_kill.get("summary")) or "ARIS kill switch is active.",
                    "discard_entry": hall_entry if hall_name == "hall_of_discard" else None,
                    "hall_name": hall_name,
                    "hall_entry": hall_entry,
                    "kill_switch": active_kill,
                }
            )
            self._record_activity({**finalized.payload(), "kind": "governance_result"})
            return finalized
        payload_ok = True
        if "ok" in payload:
            payload_ok = bool(payload.get("ok"))
        elif "returncode" in payload:
            sandbox = payload.get("sandbox") or {}
            blocked = bool(sandbox.get("blocked", False)) if isinstance(sandbox, dict) else False
            payload_ok = int(payload.get("returncode", 1)) == 0 and not blocked
        repo_changed = self._is_repo_changed_action(action)
        law_verification: dict[str, Any] | None = None
        law_context_payload = action.get("law_context")
        if isinstance(law_context_payload, dict):
            try:
                context = RuntimeLawContext(
                    request_id=str(law_context_payload.get("request_id", "")),
                    actor=str(law_context_payload.get("actor", "")),
                    claimed_identity=str(law_context_payload.get("claimed_identity", "")),
                    lineage=str(law_context_payload.get("lineage", "")),
                    legitimacy_token=str(law_context_payload.get("legitimacy_token", "")),
                    requested_scope=str(law_context_payload.get("requested_scope", "")),
                    allowed_scopes=frozenset(law_context_payload.get("allowed_scopes") or []),
                    state_present=bool(law_context_payload.get("state_present", False)),
                    code_present=bool(law_context_payload.get("code_present", False)),
                    verification_present=bool(law_context_payload.get("verification_present", False)),
                    route_name=str(law_context_payload.get("route_name", "")),
                    target=str(law_context_payload.get("target", "")),
                    session_id=str(law_context_payload.get("session_id", "")),
                    host_name=str(law_context_payload.get("host_name", "")),
                    host_version=str(law_context_payload.get("host_version", "")),
                    host_attested=bool(law_context_payload.get("host_attested", False)),
                    identity_verified=bool(law_context_payload.get("identity_verified", False)),
                    repo_changed=bool(law_context_payload.get("repo_changed", repo_changed)),
                    protected_target=bool(law_context_payload.get("protected_target", False)),
                    action_type=str(law_context_payload.get("action_type", decision.action_type)),
                    caller_claims=tuple(law_context_payload.get("caller_claims") or []),
                )
                law_verification = self.runtime_law.post_execute(
                    context=context,
                    result=payload,
                    repo_changed=repo_changed,
                    payload_ok=payload_ok,
                )
                payload["law_verification"] = law_verification
                if law_verification.get("override"):
                    active_kill = self.kill_switch.hard_kill(
                        reason="false_verification",
                        actor="runtime_law",
                        diagnostics=law_verification,
                    )
            except Exception:
                law_verification = None
        shield = self._shield_payload(
            action=action,
            integrity=decision.integrity,
            law_results=decision.law_results,
            guardrails=decision.guardrails,
            phase="finalize",
            proposed_output=payload,
            forge_eval=decision.forge_eval,
        )
        if (
            decision.allowed
            and payload_ok
            and isinstance(law_verification, dict)
            and isinstance(law_verification.get("report"), dict)
            and bool(law_verification["report"].get("false_verification", False))
        ):
            failure_reason = "False 1001 verification was detected and rejected by the verification engine."
            hall_name, hall_entry = self._record_failure_hall(
                action=action,
                fingerprint=decision.fingerprint,
                reason=failure_reason,
                law_results=decision.law_results,
                guardrails=decision.guardrails,
                forge_eval=decision.forge_eval,
                operator_decision=decision.operator_decision,
                notes="Verification may only come from the verification engine, not caller-controlled payloads.",
                failure_kind="escalation",
                metadata={"result": _serialize(payload), "law_verification": law_verification},
            )
            finalized = GovernanceDecision(
                **{
                    **self._decision_values(decision),
                    "allowed": False,
                    "verified": False,
                    "disposition": "discarded",
                    "reason": failure_reason,
                    "discard_entry": hall_entry if hall_name == "hall_of_discard" else None,
                    "hall_name": hall_name,
                    "hall_entry": hall_entry,
                    "kill_switch": active_kill,
                    "shield": shield,
                }
            )
            if self.mystic is not None:
                self.mystic.record_error(session_id=decision.session_id)
            self._record_activity({**finalized.payload(), "kind": "governance_result"})
            return finalized
        if (
            decision.allowed
            and payload_ok
            and not repo_changed
            and isinstance(law_verification, dict)
            and isinstance(law_verification.get("report"), dict)
            and not bool(law_verification["report"].get("passed", False))
        ):
            failure_reason = _text(law_verification["report"].get("reason")) or "Execution did not reach 1001."
            hall_name, hall_entry = self._record_failure_hall(
                action=action,
                fingerprint=decision.fingerprint,
                reason=failure_reason,
                law_results=decision.law_results,
                guardrails=decision.guardrails,
                forge_eval=decision.forge_eval,
                operator_decision=decision.operator_decision,
                notes="Post-execution verification rejected the action because the speech chain did not reach 1001.",
                failure_kind="escalation",
                metadata={"result": _serialize(payload), "law_verification": law_verification},
            )
            finalized = GovernanceDecision(
                **{
                    **self._decision_values(decision),
                    "allowed": False,
                    "verified": False,
                    "disposition": "discarded",
                    "reason": failure_reason,
                    "discard_entry": hall_entry if hall_name == "hall_of_discard" else None,
                    "hall_name": hall_name,
                    "hall_entry": hall_entry,
                    "kill_switch": self.kill_switch.snapshot(),
                    "shield": shield,
                }
            )
            if self.mystic is not None:
                self.mystic.record_error(session_id=decision.session_id)
            self._record_activity({**finalized.payload(), "kind": "governance_result"})
            return finalized
        if decision.allowed and payload_ok and repo_changed:
            has_verification_artifacts = self._has_verification_artifacts(payload)
            has_logbook_entry = isinstance(payload.get("logbook_entry"), dict)
            logbook_matches_change = self._logbook_entry_matches_change(
                payload=payload,
                decision=decision,
            )
            has_1001_pass = self._has_1001_pass(decision)
            if not (
                has_verification_artifacts
                and has_logbook_entry
                and logbook_matches_change
                and has_1001_pass
            ):
                failure_reason = (
                    "ARIS does not recognize repo-changing success unless the code change, "
                    "verification evidence, and Repo Logbook record agree under 1001 at finalize "
                    "time. Otherwise the action is unverified and may not be admitted as success."
                )
                hall_name, hall_entry = self._record_failure_hall(
                    action=action,
                    fingerprint=decision.fingerprint,
                    reason=failure_reason,
                    law_results=decision.law_results,
                    guardrails=decision.guardrails,
                    forge_eval=decision.forge_eval,
                    operator_decision=decision.operator_decision,
                    notes=(
                        "Undocumented or unverified repo change refused final success. "
                        "Undocumented change equals unverified change under 1001."
                    ),
                    failure_kind="escalation",
                    metadata={
                        "result": _serialize(payload),
                        "repo_changed": True,
                        "verification_artifacts_present": has_verification_artifacts,
                        "logbook_entry_present": has_logbook_entry,
                        "logbook_entry_matches_change": logbook_matches_change,
                        "meta_law_1001_pass": has_1001_pass,
                    },
                )
                finalized = GovernanceDecision(
                    **{
                        **self._decision_values(decision),
                        "allowed": False,
                        "verified": False,
                        "disposition": "discarded",
                        "reason": failure_reason,
                        "discard_entry": hall_entry if hall_name == "hall_of_discard" else None,
                        "hall_name": hall_name,
                        "hall_entry": hall_entry,
                        "kill_switch": self.kill_switch.snapshot(),
                        "shield": shield,
                    }
                )
                if self.mystic is not None:
                    self.mystic.record_error(session_id=decision.session_id)
                self._record_activity({**finalized.payload(), "kind": "governance_result"})
                return finalized
        if decision.allowed and payload_ok and not bool(shield.get("passed", False)):
            failure_reason = (
                "Shield of Truth did not admit the output as verified success."
            )
            hall_name, hall_entry = self._record_failure_hall(
                action=action,
                fingerprint=decision.fingerprint,
                reason=failure_reason,
                law_results=decision.law_results,
                guardrails=decision.guardrails,
                forge_eval=decision.forge_eval,
                operator_decision=decision.operator_decision,
                notes="Finalize-time Shield of Truth adjudication refused success.",
                failure_kind="escalation",
                metadata={"result": _serialize(payload), "shield": shield},
            )
            finalized = GovernanceDecision(
                **{
                    **self._decision_values(decision),
                    "allowed": False,
                    "verified": False,
                    "disposition": "discarded",
                    "reason": failure_reason,
                    "discard_entry": hall_entry if hall_name == "hall_of_discard" else None,
                    "hall_name": hall_name,
                    "hall_entry": hall_entry,
                    "kill_switch": self.kill_switch.snapshot(),
                    "shield": shield,
                }
            )
            if self.mystic is not None:
                self.mystic.record_error(session_id=decision.session_id)
            self._record_activity({**finalized.payload(), "kind": "governance_result"})
            return finalized
        if decision.allowed and payload_ok:
            hall_entry = self._fame(
                action=action,
                fingerprint=decision.fingerprint,
                reason="Action completed under ARIS law and returned as verified.",
                law_results=decision.law_results,
                guardrails=decision.guardrails,
                forge_eval=decision.forge_eval,
                operator_decision=decision.operator_decision,
                notes="Verified success was recorded in Hall of Fame.",
                metadata={"result": _serialize(payload)},
                lineage_key=_text(action.get("lineage_key")),
                re_evaluation_of=self._hall_reference(action.get("previous_lineage_entry")),
            )
            finalized = GovernanceDecision(
                **{
                    **self._decision_values(decision),
                    "verified": True,
                    "disposition": "verified",
                    "reason": "Action completed under ARIS law and returned as verified.",
                    "hall_name": "hall_of_fame",
                    "hall_entry": hall_entry,
                    "discard_entry": None,
                    "kill_switch": self.kill_switch.snapshot(),
                    "shield": shield,
                }
            )
            if self.mystic is not None:
                self.mystic.clear_error_streak(session_id=decision.session_id)
                self.mystic.clear_loop_streak(session_id=decision.session_id)
            self._record_activity({**finalized.payload(), "kind": "governance_result"})
            return finalized

        if not decision.allowed:
            if self.mystic is not None:
                self.mystic.record_error(session_id=decision.session_id)
            return decision

        failure_reason = _text(payload.get("error")) or _text(payload.get("stderr")) or "Action execution failed."
        hall_name, hall_entry = self._record_failure_hall(
            action=action,
            fingerprint=decision.fingerprint,
            reason=failure_reason,
            law_results=decision.law_results,
            guardrails=decision.guardrails,
            forge_eval=decision.forge_eval,
            operator_decision=decision.operator_decision,
            notes="Execution failed after approval; redesign required before re-entry.",
            failure_kind="correctness",
            metadata={"result": _serialize(payload)},
        )
        finalized = GovernanceDecision(
            **{
                **self._decision_values(decision),
                "allowed": False,
                "verified": False,
                "disposition": "discarded",
                "reason": failure_reason,
                "discard_entry": hall_entry if hall_name == "hall_of_discard" else None,
                "hall_name": hall_name,
                "hall_entry": hall_entry,
                "kill_switch": self.kill_switch.snapshot(),
                "shield": shield,
            }
        )
        if self.mystic is not None:
            self.mystic.record_error(session_id=decision.session_id)
        self._record_activity({**finalized.payload(), "kind": "governance_result"})
        return finalized

    def health_payload(self) -> dict[str, Any]:
        status = self.status_payload(include_recent=False)
        return {
            "ok": (
                bool(status["startup_ready"])
                and bool(status["integrity"].get("ok", False))
                and not bool(status["kill_switch"]["active"])
                and not bool(status["kill_switch"]["startup_blocker"])
            ),
            "system_name": status["system_name"],
            "law_mode": status["law_mode"],
            "meta_law_1001_active": status["meta_law_1001_active"],
            "operator_active": status["operator"]["active"],
            "shield_of_truth_active": status["shield_of_truth"]["active"],
            "doc_channel_active": bool(status.get("doc_channel", {}).get("active", False)),
            "memory_bank_active": status["memory_bank"]["active"],
            "evolve_engine_active": status["evolve_engine"]["active"],
            "cognitive_upgrade_active": status["cognitive_upgrade"]["active"],
            "mystic_active": status["mystic"]["active"],
            "mystic_reflection_active": status["mystic_reflection"]["active"],
            "forge_connected": status["forge"]["connected"],
            "forge_eval_connected": status["forge_eval"]["connected"],
            "repo_logbook_active": status["repo_logbook"]["active"],
            "hall_of_discard_active": status["hall_of_discard"]["active"],
            "hall_of_shame_active": status["hall_of_shame"]["active"],
            "hall_of_fame_active": status["hall_of_fame"]["active"],
            "kill_switch": status["kill_switch"],
            "startup_blockers": status["startup_blockers"],
        }

    def status_payload(self, *, include_recent: bool = True) -> dict[str, Any]:
        forge_health = self.forge.health().model_dump(exclude_none=True) if self.forge is not None else {}
        forge_eval_health = (
            self.forge_eval.health().model_dump(exclude_none=True) if self.forge_eval is not None else {}
        )
        startup = self._refresh_startup_state(lockdown_on_failure=False)
        integrity = self._current_integrity(trigger_lockdown=False)
        mystic_status = (
            self.mystic.status_payload()
            if self.mystic is not None
            else {
                "active": False,
                "component_id": "mystic.sustainment",
                "governed": False,
                "role": "human_sustainment_layer",
                "reason": _text(_MYSTIC_IMPORT_ERROR) or "Mystic sustainment unavailable.",
            }
        )
        mystic_reflection_status = (
            self.mystic_reflection.status_payload()
            if self.mystic_reflection is not None
            else {
                "active": False,
                "component_id": "mystic_reflection.core.jarvis-merged",
                "merged_with_jarvis": False,
                "governed": False,
                "role": "reflection",
                "reason": _text(_MYSTIC_REFLECTION_IMPORT_ERROR)
                or "Mystic reflection unavailable.",
            }
        )
        payload = {
            "system_name": "ARIS",
            "service_name": "Advanced Repo Intelligence Service",
            "repo_target": str(self.repo_root),
            "law_mode": "aris-1001-governed",
            "meta_law_1001_active": True,
            "foundation_law_active": True,
            "blueprint_id": BLUEPRINT_ID,
            "blueprint_rebound": BLUEPRINT_ID == "jarvis.blueprint.aris-rebound",
            "startup_ready": startup["startup_ready"],
            "startup_blockers": list(startup["startup_blockers"]),
            "guardrails": [dict(item) for item in GUARDRAILS],
            "operator": {
                "active": True,
                "fallible": True,
                "final_authority_on_risky_paths": False,
                "forge_eval_required_on_risky_paths": True,
            },
            "shield_of_truth": self.shield_of_truth.status_payload(),
            "doc_channel": self.runtime_law.doc_channel.payload(),
            "runtime_law": {
                "bootstrap": self.runtime_law.bootstrap_state.payload(),
                "ledger_path": str(self.runtime_law.ledger.path),
                "observation_mode_active": self.runtime_law.is_observation_blocked("system"),
            },
            "ul_runtime": self.runtime_law.status_payload(),
            "memory_bank": self.memory_bank.status_payload(),
            "evolve_engine": self.evolve_engine.status_payload(),
            "cognitive_upgrade": self.cognitive_upgrade.status_payload(),
            "mystic": mystic_status,
            "mystic_reflection": mystic_reflection_status,
            "forge": {
                "connected": self.forge is not None,
                "provider_configured": bool(forge_health.get("provider_configured", False)),
                "health": forge_health,
            },
            "forge_eval": {
                "connected": self.forge_eval is not None,
                "health": forge_eval_health,
            },
            "hall_of_discard": {
                "active": True,
                "count": self.hall_of_discard.count(),
            },
            "hall_of_shame": {
                "active": True,
                "count": self.hall_of_shame.count(),
            },
            "hall_of_fame": {
                "active": True,
                "count": self.hall_of_fame.count(),
            },
            "repo_logbook": self.logbook.status_payload(),
            "kill_switch": self.kill_switch.snapshot(),
            "integrity": integrity,
            "admission_contract": {
                "component": "evolving-ai",
                "role": "Governed Adaptive Engine",
                "authority": "proposal_only",
                "operator_can_override_forge_eval": False,
            },
        }
        if include_recent:
            payload["recent_activity"] = self.list_activity(limit=10)
            payload["recent_discards"] = self.hall_of_discard.list_entries(limit=10)
            payload["recent_shames"] = self.hall_of_shame.list_entries(limit=10)
            payload["recent_fame"] = self.hall_of_fame.list_entries(limit=10)
        return payload

    def list_discards(self, *, limit: int = 25) -> list[dict[str, Any]]:
        return self.hall_of_discard.list_entries(limit=limit)

    def list_shames(self, *, limit: int = 25) -> list[dict[str, Any]]:
        return self.hall_of_shame.list_entries(limit=limit)

    def list_fame(self, *, limit: int = 25) -> list[dict[str, Any]]:
        return self.hall_of_fame.list_entries(limit=limit)

    def mystic_status_payload(self, *, session_id: str) -> dict[str, Any]:
        if self.mystic is None:
            return {
                "active": False,
                "session_id": session_id,
                "reason": "Mystic sustainment is unavailable.",
            }
        payload = self.mystic.session_payload(session_id=session_id)
        payload["service"] = self.mystic.status_payload()
        payload["reflection"] = (
            self.mystic_reflection.status_payload()
            if self.mystic_reflection is not None
            else {"active": False}
        )
        return payload

    def mystic_tick(self, *, session_id: str) -> dict[str, Any]:
        if self.mystic is None:
            return self.mystic_status_payload(session_id=session_id)
        reminder = self.mystic.tick(session_id=session_id)
        if reminder is not None:
            self._record_activity(
                {
                    "kind": "mystic_reminder",
                    "session_id": session_id,
                    "mystic_signal": reminder,
                    "disposition": "observed",
                }
            )
        payload = self.mystic_status_payload(session_id=session_id)
        payload["latest_trigger"] = reminder
        return payload

    def mystic_record_break(self, *, session_id: str) -> dict[str, Any]:
        if self.mystic is None:
            return self.mystic_status_payload(session_id=session_id)
        payload = self.mystic.record_break(session_id=session_id)
        self._record_activity(
            {
                "kind": "mystic_break",
                "session_id": session_id,
                "disposition": "verified",
            }
        )
        return {
            **payload,
            "service": self.mystic.status_payload(),
        }

    def mystic_acknowledge(self, *, session_id: str) -> dict[str, Any]:
        if self.mystic is None:
            return self.mystic_status_payload(session_id=session_id)
        payload = self.mystic.acknowledge(session_id=session_id)
        self._record_activity(
            {
                "kind": "mystic_acknowledge",
                "session_id": session_id,
                "disposition": "verified",
            }
        )
        return {
            **payload,
            "service": self.mystic.status_payload(),
        }

    def mystic_mute(self, *, session_id: str, minutes: float) -> dict[str, Any]:
        if self.mystic is None:
            return self.mystic_status_payload(session_id=session_id)
        payload = self.mystic.mute_for_minutes(session_id=session_id, minutes=minutes)
        self._record_activity(
            {
                "kind": "mystic_mute",
                "session_id": session_id,
                "minutes": minutes,
                "disposition": "verified",
            }
        )
        return {
            **payload,
            "service": self.mystic.status_payload(),
        }

    def record_repo_logbook_entry(
        self,
        *,
        title: str,
        what_changed: list[str],
        why_it_changed: list[str],
        how_it_changed: list[str],
        files_changed: list[str],
        verification: list[str],
        remaining_risks: list[str],
        action_id: str = "",
        fingerprint: str = "",
    ) -> dict[str, Any]:
        entry = self.logbook.append_entry(
            title=title,
            what_changed=what_changed,
            why_it_changed=why_it_changed,
            how_it_changed=how_it_changed,
            files_changed=files_changed,
            verification=verification,
            remaining_risks=remaining_risks,
            action_id=action_id,
            fingerprint=fingerprint,
        )
        self._record_activity(
            {
                "kind": "logbook_entry",
                "title": title,
                "action_id": action_id,
                "fingerprint": fingerprint,
                "path": entry["path"],
                "recorded_at": entry["recorded_at"],
                "disposition": "verified",
            }
        )
        return entry

    def activate_soft_kill(self, *, reason: str, actor: str = "manual") -> dict[str, Any]:
        snapshot = self.kill_switch.soft_kill(reason=reason, actor=actor)
        self._record_activity(
            {
                "kind": "kill_switch",
                "mode": "soft_kill",
                "reason": reason,
                "actor": actor,
                "disposition": "verified",
                "risky": True,
            }
        )
        return snapshot

    def activate_hard_kill(self, *, reason: str, actor: str = "manual") -> dict[str, Any]:
        snapshot = self.kill_switch.hard_kill(reason=reason, actor=actor)
        self._record_activity(
            {
                "kind": "kill_switch",
                "mode": "hard_kill",
                "reason": reason,
                "actor": actor,
                "disposition": "verified",
                "risky": True,
            }
        )
        return snapshot

    def reset_kill_switch(
        self,
        *,
        reason: str,
        actor: str = "admin",
        reseal_integrity: bool = False,
    ) -> dict[str, Any]:
        startup = self._refresh_startup_state(
            lockdown_on_failure=False,
            reseal_integrity=reseal_integrity,
        )
        return self.kill_switch.reset(
            actor=actor,
            reason=reason,
            integrity_verified=bool(startup.get("startup_ready", False)),
            diagnostics={"startup": startup, "resealed": reseal_integrity},
        )

    def forge_repo_plan(
        self,
        *,
        goal: str,
        focus_paths: list[str] | None = None,
        operation_mode: str = "repo_manager",
    ) -> dict[str, Any]:
        if self.forge is None:
            return {
                "ok": False,
                "error": "Forge is not available in this runtime.",
                "forge": {"connected": False, "import_error": _text(_FORGE_IMPORT_ERROR)},
                "route": [
                    {"stage": "Jarvis Blueprint", "status": "ready"},
                    {"stage": "Operator", "status": "approved"},
                    {"stage": "Forge", "status": "unavailable"},
                    {"stage": "Forge Eval", "status": "proposal_only"},
                    {"stage": "Outcome", "status": "failed"},
                ],
            }
        context = self._build_repo_context(goal=goal, focus_paths=focus_paths or [])
        response, status_code, trace_id = self.forge.handle_contractor_request(
            {
                "task_id": f"aris_repo_{uuid.uuid4().hex[:10]}",
                "kind": "repo_manager",
                "context": {
                    "goal": goal,
                    "files": context["files"],
                    "focus_files": context["focus_files"],
                    "target_scope": "Evolving AI repo",
                    "change_intent": operation_mode,
                    "validation_target": "ARIS governed repo plan",
                    "operation_mode": operation_mode,
                    "constraints": {
                        "profile": "default",
                        "max_output_chars": 8000,
                    },
                    "file_path_allowlist": context["focus_files"],
                    "no_execution_without_handoff": True,
                },
            }
        )
        payload = response.model_dump(exclude_none=True)
        payload["ok"] = status_code == 200
        payload["status_code"] = status_code
        payload["trace_id"] = trace_id
        payload["repo_context"] = context
        payload["route"] = [
            {"stage": "Jarvis Blueprint", "status": "ready"},
            {"stage": "Operator", "status": "approved"},
            {"stage": "Forge", "status": "completed" if status_code == 200 else "failed"},
            {"stage": "Forge Eval", "status": "proposal_only"},
            {"stage": "Outcome", "status": "proposal_ready" if status_code == 200 else "failed"},
        ]
        repo_manager = payload.get("result", {}).get("repo_manager", {}) if isinstance(payload.get("result"), dict) else {}
        plan_reason = (
            _text(repo_manager.get("repo_summary"))
            or _text(payload.get("message"))
            or (
                _text(payload.get("error", {}).get("message"))
                if isinstance(payload.get("error"), dict)
                else _text(payload.get("error"))
            )
            or ("Forge repo plan ready for review." if status_code == 200 else "Forge repo plan failed.")
        )
        self._record_activity(
            {
                "kind": "forge_repo_plan",
                "action_type": "forge_repo_plan",
                "goal": goal,
                "purpose": "Generate a governed Forge repo plan without applying changes.",
                "target": "Evolving AI repo",
                "focus_files": context["focus_files"],
                "status_code": status_code,
                "ok": status_code == 200,
                "trace_id": trace_id,
                "reason": plan_reason,
                "disposition": "proposal_ready" if status_code == 200 else "blocked",
                "requires_forge_eval": False,
                "verified": False,
                "route": payload["route"],
            }
        )
        return payload

    def _build_repo_context(self, *, goal: str, focus_paths: list[str]) -> dict[str, Any]:
        candidate_paths = [
            "pyproject.toml",
            "evolving_ai/aris/runtime.py",
            "evolving_ai/aris/service.py",
            "evolving_ai/aris/launcher.py",
            "evolving_ai/app/server.py",
            "evolving_ai/app/service.py",
            "evolving_ai/app/static/index.html",
            "evolving_ai/app/static/app.js",
            "evolving_ai/app/static/app.css",
            "forge/service.py",
            "forge_eval/service.py",
            "tests/test_aris_governance.py",
        ]
        ordered: list[str] = []
        seen: set[str] = set()
        for path in [*focus_paths, *candidate_paths]:
            normalized = _text(path).replace("\\", "/")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        files: list[dict[str, Any]] = []
        for relative in ordered:
            target = (self.repo_root / relative).resolve()
            if not target.exists() or not target.is_file():
                continue
            try:
                content = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            files.append(
                {
                    "path": relative,
                    "content": content[:12000],
                    "truncated": len(content) > 12000,
                }
            )
            if len(files) >= 12:
                break
        return {
            "goal": goal,
            "focus_files": [item["path"] for item in files],
            "files": files,
        }

    def action_for_file_change(
        self,
        *,
        action_type: str,
        session_id: str,
        purpose: str,
        path: str,
        before: str,
        after: str,
        source: str,
        operator_decision: str = "approved",
    ) -> dict[str, Any]:
        relative = _text(path).replace("\\", "/")
        return {
            "action_type": action_type,
            "session_id": session_id,
            "purpose": purpose,
            "target": relative,
            "patch": _build_unified_diff(relative or "workspace-file", before, after),
            "source": source,
            "operator_decision": operator_decision,
            "authorized": True,
            "observed": True,
            "bounded": True,
        }
