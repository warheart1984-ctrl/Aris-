"""Smoke checks for CoGOS recovery mode."""

from __future__ import annotations

from recovery_mode import RecoveryMode


def main() -> int:
    recovery = RecoveryMode()
    status = recovery.status()
    assert status["ok"]
    verify = recovery.verify()
    assert verify["ok"], verify
    enabled = recovery.enable()
    assert enabled["ok"] and enabled["enabled"]
    assert recovery.status()["recovery_flag"]
    disabled = recovery.disable()
    assert disabled["ok"] and not disabled["enabled"]
    boot = recovery.boot_recovery()
    assert boot["ok"] and boot["mode"] == "recovery"
    assert recovery.proof.exists()
    print("recovery_smoke: ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

