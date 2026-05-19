"""Smoke checks for the guarded CoGOS installer."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from governance_invariant_engine import cogos_root


def _installer_path() -> Path:
    root = cogos_root()
    payload = root.parent.parent if root.name == "cogos" and root.parent.name == "opt" else root
    return payload / "usr" / "local" / "bin" / "cogos-install"


def main() -> int:
    installer = _installer_path()
    assert installer.exists(), installer
    text = installer.read_text(encoding="utf-8")
    for needle in (
        "apply --target",
        "--confirm-erase",
        "validate_target",
        "install_bootloader",
        "write_proof",
        "COGOSDATA",
    ):
        assert needle in text, needle

    if os.name != "nt":
        help_run = subprocess.run(["sh", str(installer), "--help"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert help_run.returncode == 0
        assert "cogos-install plan" in help_run.stdout
        plan_run = subprocess.run(
            ["sh", str(installer), "plan", "--target", "/dev/sdz", "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # /dev/sdz may not exist; plan is allowed to render a structural plan
        # for UI previews, while validate/apply performs hard block-device checks.
        data = json.loads(plan_run.stdout)
        assert data["destructive"] is True
        assert data["partitions"][2]["label"] == "COGOSDATA"

    print("installer_smoke: ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
