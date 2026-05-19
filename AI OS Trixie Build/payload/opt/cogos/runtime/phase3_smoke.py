#!/usr/bin/env python3
"""Phase 3 smoke tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("COGOS_ROOT", str(ROOT))
sys.path.insert(0, str(ROOT / "runtime"))

from compute_tiers import ComputeTierEngine  # noqa: E402
from cogos_pkg import install, list_packages, remove  # noqa: E402
from cogos_backup import export_backup, list_backups  # noqa: E402
from cogos_runtime import CognitiveRuntime  # noqa: E402
from eval_harness import run_eval_suite  # noqa: E402
from operator_cockpit import full_cockpit  # noqa: E402
from phase3_panels import phase3_status  # noqa: E402


def main() -> int:
    tiers = ComputeTierEngine()
    assert tiers.resolve_tier("operator") == "elevated"
    assert not tiers.check("ul.dangerous", profile_id="kid").allowed
    assert tiers.check("creative.story_draft", profile_id="kid").allowed

    inst = install("operator_notes", profile_id="operator")
    assert inst["ok"], inst
    assert any(p["installed"] for p in list_packages() if p["id"] == "operator_notes")
    rem = remove("operator_notes", profile_id="operator")
    assert rem["ok"]

    exp = export_backup("phase3-smoke", profile_id="operator")
    assert exp["ok"] and Path(exp["path"]).exists()
    assert list_backups()

    rt = CognitiveRuntime()
    assert rt.boot()
    rt.switch_profile("kid")
    rt.set_mode("automatic")
    blocked_kid = rt.process("substrate: repo deletes x1")
    assert "tier" in blocked_kid.lower() or "GOVERNANCE BLOCK" in blocked_kid, blocked_kid
    rt.switch_profile("operator")

    status = phase3_status()
    assert status["release"].get("version")
    cockpit = full_cockpit()
    assert "phase3" in cockpit

    eval_report = run_eval_suite()
    assert eval_report.get("ok"), eval_report

    print("phase3_smoke: ALL PASSED")
    print(json.dumps({"tier": tiers.resolve_tier("operator"), "eval": eval_report["passed"], "release": status["release"]["version"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
