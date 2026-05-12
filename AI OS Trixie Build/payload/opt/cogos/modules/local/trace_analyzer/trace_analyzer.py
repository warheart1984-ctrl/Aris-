#!/usr/bin/env python3
"""Readonly trace analyzer sample module."""

from __future__ import annotations

import json
import pathlib


TRACE = pathlib.Path("/opt/cogos/memory/traces/aris_cycles.jsonl")


def main() -> int:
    count = 0
    if TRACE.exists():
        count = len([line for line in TRACE.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()])
    print(json.dumps({"module": "trace_analyzer", "trace_count": count}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
