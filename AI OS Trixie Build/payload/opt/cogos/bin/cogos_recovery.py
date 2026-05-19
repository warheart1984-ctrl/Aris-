#!/usr/bin/env python3
"""CoGOS recovery mode CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
RUNTIME = ROOT / "runtime"
for p in (RUNTIME, RUNTIME / "ul", RUNTIME / "voss"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from recovery_mode import RecoveryMode  # noqa: E402
from cogos_backup import list_backups  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CoGOS recovery mode")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("verify")
    sub.add_parser("enable")
    sub.add_parser("disable")
    sub.add_parser("snapshots")
    sub.add_parser("backups")
    rb = sub.add_parser("rollback")
    rb.add_argument("snapshot")
    restore = sub.add_parser("restore-backup")
    restore.add_argument("bundle")
    restore.add_argument("--profile", default="operator")
    sub.add_parser("reset-first-run")
    sub.add_parser("boot")
    ns = parser.parse_args(argv)

    recovery = RecoveryMode()
    if ns.cmd == "status":
        out = recovery.status()
    elif ns.cmd == "verify":
        out = recovery.verify()
    elif ns.cmd == "enable":
        out = recovery.enable()
    elif ns.cmd == "disable":
        out = recovery.disable()
    elif ns.cmd == "snapshots":
        out = {"ok": True, "snapshots": recovery.list_snapshots()}
    elif ns.cmd == "backups":
        out = {"ok": True, "backups": list_backups()}
    elif ns.cmd == "rollback":
        out = recovery.apply_rollback(ns.snapshot)
    elif ns.cmd == "restore-backup":
        out = recovery.restore_backup(ns.bundle, profile_id=ns.profile)
    elif ns.cmd == "reset-first-run":
        out = recovery.reset_first_run()
    elif ns.cmd == "boot":
        out = recovery.boot_recovery()
    else:
        return 2
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
