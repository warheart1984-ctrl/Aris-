#!/usr/bin/env python3
"""CoGOS creative lanes CLI (Phase 2)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
RUNTIME = ROOT / "runtime"
for p in (RUNTIME, RUNTIME / "ul", RUNTIME / "voss"):
    sys.path.insert(0, str(p))

from creative_modules import run_creative  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="CoGOS creative lanes")
    parser.add_argument("lane", choices=["story_forge", "beatbox", "world3d"])
    parser.add_argument("verb", help="e.g. drafts, scores, builds")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_creative(args.lane, args.verb, prompt=args.prompt)
    out = {
        "ok": result.ok,
        "lane": result.lane,
        "summary": result.summary,
        "artifact_path": result.artifact_path,
        "details": result.details,
    }
    print(json.dumps(out, indent=2) if args.json else result.summary)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
