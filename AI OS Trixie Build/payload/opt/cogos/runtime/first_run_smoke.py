"""Smoke checks for the CoGOS first-run wizard."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from first_run_wizard import FirstRunWizard
from governance_invariant_engine import cogos_root


def main() -> int:
    root = cogos_root()
    wizard = FirstRunWizard()
    backup = {
        "users": (root / "config" / "users.json").read_text(encoding="utf-8-sig"),
        "boot": (root / "config" / "boot_profile.json").read_text(encoding="utf-8-sig") if (root / "config" / "boot_profile.json").exists() else "{}",
        "state": (root / "config" / "first_run.json").read_text(encoding="utf-8-sig") if (root / "config" / "first_run.json").exists() else None,
        "hostname": (root / "config" / "hostname.json").read_text(encoding="utf-8-sig") if (root / "config" / "hostname.json").exists() else None,
        "automatic": (root / "memory" / "automatic" / "state.json").read_text(encoding="utf-8-sig") if (root / "memory" / "automatic" / "state.json").exists() else None,
        "proof": (root / "memory" / "logs" / "first_run_proof.json").read_text(encoding="utf-8-sig") if (root / "memory" / "logs" / "first_run_proof.json").exists() else None,
    }
    try:
        result = wizard.apply(
            hostname="cogos-smoke",
            profile_id="operator",
            display_name="Operator",
            mode_default="manual",
            workspace_name="First Run Smoke",
            enable_kid=True,
        )
        assert result["ok"]
        status = wizard.status()
        assert status["completed"]
        assert (root / "memory" / "logs" / "first_run_proof.json").exists()
        users = json.loads((root / "config" / "users.json").read_text(encoding="utf-8-sig"))
        assert users["active_profile"] == "operator"
        assert "kid" in users["profiles"]
        print("first_run_smoke: ALL PASSED")
        return 0
    finally:
        (root / "config" / "users.json").write_text(backup["users"], encoding="utf-8")
        (root / "config" / "boot_profile.json").write_text(backup["boot"], encoding="utf-8")
        state_path = root / "config" / "first_run.json"
        if backup["state"] is None:
            state_path.unlink(missing_ok=True)
        else:
            state_path.write_text(backup["state"], encoding="utf-8")
        hostname_path = root / "config" / "hostname.json"
        if backup["hostname"] is None:
            hostname_path.unlink(missing_ok=True)
        else:
            hostname_path.write_text(backup["hostname"], encoding="utf-8")
        automatic_path = root / "memory" / "automatic" / "state.json"
        if backup["automatic"] is None:
            automatic_path.unlink(missing_ok=True)
        else:
            automatic_path.write_text(backup["automatic"], encoding="utf-8")
        proof_path = root / "memory" / "logs" / "first_run_proof.json"
        if backup["proof"] is None:
            proof_path.unlink(missing_ok=True)
        else:
            proof_path.write_text(backup["proof"], encoding="utf-8")
        shutil.rmtree(root / "memory" / "workspaces" / "first-run-smoke", ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
