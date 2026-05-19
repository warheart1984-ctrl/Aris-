#!/usr/bin/env python3
"""CoGOS governed backup export/import (Phase 3)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
sys.path.insert(0, str(ROOT / "runtime"))

from cogos_backup import export_backup, import_backup, list_backups  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="CoGOS governed backup")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("list")
    exp = sub.add_parser("export")
    exp.add_argument("--label", default="operator")
    exp.add_argument("--profile", default="operator")
    imp = sub.add_parser("import")
    imp.add_argument("bundle_path")
    imp.add_argument("--profile", default="operator")
    args = parser.parse_args()

    if args.cmd == "list":
        print(json.dumps(list_backups(), indent=2))
        return 0
    if args.cmd == "export":
        print(json.dumps(export_backup(args.label, profile_id=args.profile), indent=2))
        return 0
    if args.cmd == "import":
        print(json.dumps(import_backup(args.bundle_path, profile_id=args.profile), indent=2))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
