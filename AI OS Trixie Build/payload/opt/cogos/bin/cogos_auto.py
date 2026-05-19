#!/usr/bin/env python3
"""CoGOS Automatic mode CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from automatic_mode import AutomaticModeEngine  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="CoGOS Automatic mode")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    ws = sub.add_parser("workspace")
    ws.add_argument("name")

    org = sub.add_parser("organize")
    org.add_argument("source")
    org.add_argument("--workspace")
    org.add_argument("--apply", action="store_true")

    rem = sub.add_parser("remember")
    rem.add_argument("key")
    rem.add_argument("value")
    rem.add_argument("--workspace")

    sub.add_parser("suggest")

    args = parser.parse_args()
    engine = AutomaticModeEngine()
    if args.cmd == "status":
        out = engine.status()
    elif args.cmd == "workspace":
        out = engine.create_workspace(args.name)
    elif args.cmd == "organize":
        out = engine.organize_files(args.source, workspace_id=args.workspace, apply=args.apply)
    elif args.cmd == "remember":
        out = engine.remember(args.key, args.value, workspace_id=args.workspace)
    elif args.cmd == "suggest":
        out = engine.suggest_workflows()
    else:
        parser.error("unknown command")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())

