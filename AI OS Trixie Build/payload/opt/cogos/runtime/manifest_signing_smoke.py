"""Smoke checks for signed CoGOS manifests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from governance_invariant_engine import cogos_root
from manifest_signing import sign_manifest_file, verify_core_manifests, verify_manifest_file


def main() -> int:
    root = cogos_root()
    core = verify_core_manifests(root)
    assert core["ok"], core

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "manifest.json"
        path.write_text(json.dumps({"name": "smoke", "version": "1.0"}, indent=2), encoding="utf-8")
        sig = sign_manifest_file(path)
        assert sig["signature"]
        assert verify_manifest_file(path)["ok"]
        path.write_text(json.dumps({"name": "smoke", "version": "tampered"}, indent=2), encoding="utf-8")
        assert not verify_manifest_file(path)["ok"]

    print("manifest_signing_smoke: ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
