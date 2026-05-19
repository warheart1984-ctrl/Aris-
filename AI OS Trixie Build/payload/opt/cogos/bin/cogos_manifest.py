#!/usr/bin/env python3
"""Sign and verify CoGOS manifests."""

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

from manifest_signing import sign_manifest_file, verify_core_manifests, verify_manifest_file  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CoGOS manifest signing")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sign = sub.add_parser("sign")
    sign.add_argument("path")
    verify = sub.add_parser("verify")
    verify.add_argument("path", nargs="?")
    sub.add_parser("verify-core")
    ns = parser.parse_args(argv)

    if ns.cmd == "sign":
        out = sign_manifest_file(Path(ns.path))
        out["ok"] = True
    elif ns.cmd == "verify":
        out = verify_manifest_file(Path(ns.path)) if ns.path else verify_core_manifests(ROOT)
    elif ns.cmd == "verify-core":
        out = verify_core_manifests(ROOT)
    else:
        return 2
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
