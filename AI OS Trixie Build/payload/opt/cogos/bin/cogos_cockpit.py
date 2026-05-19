#!/usr/bin/env python3
"""Full operator cockpit — Phase 0–3 unified status."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
sys.path.insert(0, str(ROOT / "runtime"))

from operator_cockpit import cockpit_summary_lines, full_cockpit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.json:
        print(json.dumps(full_cockpit(), indent=2))
    else:
        print("CoGOS Operator Cockpit (Phase 0–3)")
        print("=" * 50)
        for line in cockpit_summary_lines():
            print(line)
        print()
        print("Commands: cogos-desktop-start | cogos_eval.py run | cogos_pkg.py list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
