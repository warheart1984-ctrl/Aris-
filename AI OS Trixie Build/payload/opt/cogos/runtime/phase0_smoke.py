#!/usr/bin/env python3
"""Phase 0 smoke tests — run from payload with COGOS_ROOT set."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("COGOS_ROOT", str(ROOT))
RUNTIME = ROOT / "runtime"
for p in (RUNTIME, RUNTIME / "ul", RUNTIME / "voss"):
    sys.path.insert(0, str(p))

from cogos_runtime import CognitiveRuntime  # noqa: E402


def main() -> int:
    rt = CognitiveRuntime()
    assert rt.boot(), "boot failed"

    ok_ping = rt.process("substrate: agent pings x1")
    assert "GOVERNANCE BLOCK" not in ok_ping, ok_ping
    assert "UL OK" in ok_ping or "executed" in ok_ping.lower(), ok_ping

    rt.set_mode("automatic")
    blocked = rt.process("substrate: repo deletes x1")
    assert "GOVERNANCE BLOCK" in blocked, blocked

    rt.set_mode("manual")
    manual = rt.process("substrate: repo deletes x1")
    assert "GOVERNANCE BLOCK" not in manual or "UL OK" in manual, manual

    verify = rt.ledger.verify_chain()
    assert verify.get("ok"), verify

    print("phase0_smoke: ALL PASSED")
    print(rt.status())
    return 0


if __name__ == "__main__":
    sys.exit(main())
