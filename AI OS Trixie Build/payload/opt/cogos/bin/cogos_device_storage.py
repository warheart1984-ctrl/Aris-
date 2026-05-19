#!/usr/bin/env python3
"""CLI for CoGOS Device + Storage Manager MVP."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from device_storage_manager import DeviceStorageManager  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CoGOS Device + Storage Manager")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("plans")
    mount = sub.add_parser("plan-mount")
    mount.add_argument("device")
    mount.add_argument("--mountpoint", default="")
    exec_mount = sub.add_parser("mount")
    exec_mount.add_argument("device")
    exec_mount.add_argument("--mountpoint", default="")
    exec_mount.add_argument("--read-write", action="store_true")
    exec_mount.add_argument("--yes", action="store_true")
    exec_mount.add_argument("--confirm-mount", default="")
    unmount = sub.add_parser("unmount")
    unmount.add_argument("mountpoint")
    unmount.add_argument("--yes", action="store_true")
    unmount.add_argument("--confirm-unmount", default="")
    archive = sub.add_parser("plan-archive")
    archive.add_argument("source")
    archive.add_argument("--label", default="archive")
    cleanup = sub.add_parser("plan-cleanup")
    cleanup.add_argument("target")
    ns = parser.parse_args(argv)

    manager = DeviceStorageManager()
    if ns.cmd == "status":
        out = manager.inventory()
    elif ns.cmd == "plans":
        out = {"ok": True, "plans": manager.list_plans()}
    elif ns.cmd == "plan-mount":
        out = manager.plan_mount(ns.device, ns.mountpoint)
    elif ns.cmd == "mount":
        out = manager.execute_mount(
            ns.device,
            ns.mountpoint,
            readonly=not ns.read_write,
            yes=ns.yes,
            confirm=ns.confirm_mount,
        )
    elif ns.cmd == "unmount":
        out = manager.execute_unmount(ns.mountpoint, yes=ns.yes, confirm=ns.confirm_unmount)
    elif ns.cmd == "plan-archive":
        out = manager.plan_archive(ns.source, ns.label)
    elif ns.cmd == "plan-cleanup":
        out = manager.plan_cleanup(ns.target)
    else:
        return 2
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
