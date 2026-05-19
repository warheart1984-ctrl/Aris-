#!/usr/bin/env python3
"""CoGOS governed package manager (Phase 3)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
sys.path.insert(0, str(ROOT / "runtime"))

from cogos_pkg import install, list_packages, remove, verify_catalog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="CoGOS governed packages")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("list")
    sub.add_parser("verify")
    inst = sub.add_parser("install")
    inst.add_argument("package_id")
    inst.add_argument("--profile", default="operator")
    rem = sub.add_parser("remove")
    rem.add_argument("package_id")
    rem.add_argument("--profile", default="operator")
    args = parser.parse_args()

    if args.cmd == "list":
        print(json.dumps(list_packages(), indent=2))
        return 0
    if args.cmd == "verify":
        out = verify_catalog()
        print(json.dumps(out, indent=2))
        return 0 if out.get("ok") else 1
    if args.cmd == "install":
        print(json.dumps(install(args.package_id, profile_id=args.profile), indent=2))
        return 0
    if args.cmd == "remove":
        print(json.dumps(remove(args.package_id, profile_id=args.profile), indent=2))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
