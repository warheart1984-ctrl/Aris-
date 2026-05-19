#!/usr/bin/env python3
"""CLI for UL stdlib v0.1."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
for rel in ("runtime", "runtime/ul"):
    p = ROOT / rel
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from ul_stdlib import call_stdlib, stdlib_manifest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CoGOS UL stdlib v0.1")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest")
    call = sub.add_parser("call")
    call.add_argument("name")
    call.add_argument("args", nargs="*")
    sub.add_parser("demo")
    ns = parser.parse_args(argv)

    if ns.cmd == "manifest":
        print(json.dumps(stdlib_manifest(), indent=2, sort_keys=True))
        return 0
    if ns.cmd == "call":
        print(json.dumps(call_stdlib(ns.name, ns.args), indent=2, sort_keys=True, default=str))
        return 0
    if ns.cmd == "demo":
        rows = {
            "now": call_stdlib("core.now"),
            "workspace": call_stdlib("auto.workspace", ["UL stdlib demo"]),
            "remember": call_stdlib("state.remember", ["demo", "UL stdlib v0.1"]),
            "recall": call_stdlib("state.recall", ["demo"]),
        }
        print(json.dumps(rows, indent=2, sort_keys=True, default=str))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

