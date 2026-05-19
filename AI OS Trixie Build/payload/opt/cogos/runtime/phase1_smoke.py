#!/usr/bin/env python3
"""Phase 1 smoke tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("COGOS_ROOT", str(ROOT))
RUNTIME = ROOT / "runtime"
for p in (RUNTIME, RUNTIME / "ul", RUNTIME / "voss"):
    sys.path.insert(0, str(p))

from cogos_runtime import CognitiveRuntime  # noqa: E402
from determinism_corridor import run_boot_verification  # noqa: E402
from hal_service import observe_hal, write_hal_snapshot  # noqa: E402
from net_gre import NetFlow, NetGRE  # noqa: E402
from phase1_panels import phase1_status  # noqa: E402
from user_profiles import UserProfileManager  # noqa: E402


def main() -> int:
    rt = CognitiveRuntime()
    assert rt.boot(), "cognitive boot failed"

    profiles = UserProfileManager()
    profiles.set_active("kid")
    kid = profiles.get_active()
    assert kid.id == "kid"
    profiles.set_active("operator")

    net = NetGRE()
    ok_flow = net.evaluate(NetFlow("outbound", "tcp", "127.0.0.1", 443, profile_id="operator"))
    assert ok_flow.allowed
    bad_flow = net.evaluate(NetFlow("outbound", "tcp", "evil.example", 23, profile_id="kid"))
    assert not bad_flow.allowed

    snap = write_hal_snapshot(observe_hal())
    assert snap.exists()

    panels = phase1_status()
    assert "operator_dashboard" in panels
    assert "governance_timeline" in panels
    assert "law_pulse" in panels

    corridor = run_boot_verification()
    assert corridor.get("ok"), corridor

    rt.switch_profile("kid")
    assert rt.profiles.active_id == "kid"
    rt.switch_profile("operator")

    print("phase1_smoke: ALL PASSED")
    print(json.dumps(rt.status(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
