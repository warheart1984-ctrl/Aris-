#!/usr/bin/env python3
"""CoGOS ship preflight - final gate before Debian remaster."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
sys.path.insert(0, str(ROOT / "runtime"))

from ship_preflight import run_preflight, summary_lines  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", nargs="?", default="preflight", choices=["preflight", "report"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report_path = ROOT / "memory" / "logs" / "ship_preflight.json"
    if args.cmd == "report":
        if report_path.exists():
            print(report_path.read_text(encoding="utf-8"))
            return 0
        print("{}")
        return 1

    report = run_preflight()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("\n".join(summary_lines(report)))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
