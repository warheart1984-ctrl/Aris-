#!/usr/bin/env python3
"""CoGOS eval harness — ship readiness verification (Phase 3)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
sys.path.insert(0, str(ROOT / "runtime"))

from eval_harness import run_eval_suite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", nargs="?", default="run", choices=["run", "report"])
    args = parser.parse_args()

    if args.cmd == "report":
        path = ROOT / "memory" / "logs" / "eval_report.json"
        if path.exists():
            print(path.read_text(encoding="utf-8"))
        else:
            print("{}")
        return 0

    report = run_eval_suite()
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
