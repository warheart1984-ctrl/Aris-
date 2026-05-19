#!/usr/bin/env python3
"""Phase 2 smoke tests."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("COGOS_ROOT", str(ROOT))
RUNTIME = ROOT / "runtime"
for p in (RUNTIME, RUNTIME / "ul", RUNTIME / "voss"):
    sys.path.insert(0, str(p))

from cogos_runtime import CognitiveRuntime  # noqa: E402
from creative_modules import run_creative  # noqa: E402
from mesh_identity import MeshIdentityStore  # noqa: E402
from reasoning_exchange import ReasoningExchangeNode  # noqa: E402
from phase2_panels import creative_status, mesh_status, phase2_status  # noqa: E402


def main() -> int:
    ident = MeshIdentityStore().load_or_create()
    assert len(ident.device_sigil) == 64

    sf = run_creative("story_forge", "drafts", prompt="dragon game")
    assert sf.ok and Path(sf.artifact_path).exists()

    bb = run_creative("beatbox", "scores")
    assert bb.ok

    w3 = run_creative("world3d", "builds", prompt="forest arena")
    assert w3.ok

    node = ReasoningExchangeNode()
    msg = node.propose({"hypothesis": "test", "confidence": 0.5})
    result = node.receive(msg.to_dict())
    assert result.admitted

    peer_id = "peer-test-device"
    node.trust_peer(peer_id)
    peer_sigil = __import__("mesh_identity", fromlist=["device_sigil"]).device_sigil(peer_id)
    ext = node.propose({"ping": True}, kind="health_ping")
    ext.from_sigil = peer_sigil
    ext_dict = ext.to_dict()
    ext_dict["from_sigil"] = peer_sigil
    admitted = node.receive(ext_dict)
    assert admitted.admitted

    rt = CognitiveRuntime()
    assert rt.boot()
    out = rt.process("Nova, make a dragon game")
    assert "CREATIVE OK" in out or "story_forge" in out.lower(), out

    ul = rt.process("substrate: nova drafts x1")
    assert "UL OK" in ul or "CREATIVE" in ul, ul

    assert creative_status()["artifacts_total"] >= 3
    assert phase2_status()["mesh"]["identity"]

    print("phase2_smoke: ALL PASSED")
    print(json.dumps(phase2_status(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
