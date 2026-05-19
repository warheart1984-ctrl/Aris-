"""Smoke tests for UL stdlib v0.1."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from governance_invariant_engine import cogos_root

ROOT = cogos_root()
for rel in ("runtime", "runtime/ul"):
    p = ROOT / rel
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from ul_lang import run_traced  # noqa: E402
from ul_stdlib import call_stdlib, stdlib_manifest  # noqa: E402
from ul_stdlib_substrate import apply_stdlib_verbs_to_substrate, register_stdlib_handlers  # noqa: E402
from ul_substrate import ForgeGate, SubstrateRuntime  # noqa: E402


def main() -> int:
    manifest = stdlib_manifest()
    assert manifest["version"] == "0.1.0"
    assert "auto.workspace" in manifest["groups"]["auto"]

    remembered = call_stdlib("state.remember", ["smoke", "ok"])
    assert remembered["ok"]
    assert call_stdlib("state.recall", ["smoke"]) == "ok"

    workspace = call_stdlib("auto.workspace", ["UL stdlib smoke"])
    assert workspace["ok"]

    source = """\
set stamp to ul_now()
print ul_slug("UL Stdlib Smoke")
print ul_recall("smoke")
"""
    _, tracer = run_traced(source)
    assert "ul-stdlib-smoke" in tracer.output_lines
    assert "ok" in tracer.output_lines

    apply_stdlib_verbs_to_substrate()
    rt = SubstrateRuntime(gate=ForgeGate())
    register_stdlib_handlers(rt)
    result = rt.execute(
        "agent remembers x1\nagent recalls x1\nsystem reports x1\nagent notices x1",
        context={"memory_key": "substrate-smoke", "memory_value": "ok", "notice": "stdlib substrate ok"},
    )
    assert result.allowed
    assert not result.error
    assert len(result.outputs) == 4

    workspace_path = Path(workspace["workspace"].get("path", ""))
    workspace_root = ROOT / "memory" / "workspaces"
    try:
        if workspace_path.resolve().is_relative_to(workspace_root.resolve()):
            shutil.rmtree(workspace_path, ignore_errors=True)
            state_path = ROOT / "memory" / "automatic" / "state.json"
            if state_path.exists():
                import json

                data = json.loads(state_path.read_text(encoding="utf-8-sig"))
                data.get("workspaces", {}).pop("ul-stdlib-smoke", None)
                if data.get("active_workspace") == "ul-stdlib-smoke":
                    data["active_workspace"] = None
                state_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        pass

    print("UL stdlib v0.1 smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
