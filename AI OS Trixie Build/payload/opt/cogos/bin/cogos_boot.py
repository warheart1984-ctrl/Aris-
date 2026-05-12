#!/usr/bin/env python3
"""Project Infi / ARIS governed boot harness.

This is intentionally small. It proves the staged OS payload can load law,
open the current runtime files, emit a governed boot report, and fail closed
when required files are missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
from typing import Any


ROOT = pathlib.Path("/opt/cogos")
REQUIRED = [
    ROOT / "law" / "root_law.json",
    ROOT / "law" / "boot_law.json",
    ROOT / "law" / "governance_rules.json",
    ROOT / "law" / "law_manifest.json",
    ROOT / "config" / "runtime.json",
    ROOT / "config" / "module_manifest.json",
    ROOT / "runtime" / "aais_unified.py",
    ROOT / "runtime" / "aris_runtime.py",
    ROOT / "runtime" / "ul_core.py",
    ROOT / "runtime" / "forge_eval.py",
]


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def verify_payload() -> dict[str, Any]:
    missing = [str(p) for p in REQUIRED if not p.exists()]
    if missing:
        return {"ok": False, "stage": "payload", "missing": missing}

    files = []
    for path in REQUIRED:
        files.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    root_law = load_json(ROOT / "law" / "root_law.json")
    boot_law = load_json(ROOT / "law" / "boot_law.json")
    governance = load_json(ROOT / "law" / "governance_rules.json")
    law_manifest = load_json(ROOT / "law" / "law_manifest.json")
    manifest = load_json(ROOT / "config" / "module_manifest.json")

    return {
        "ok": True,
        "stage": "governed_ready",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root_law": root_law.get("name"),
        "boot_sequence": boot_law.get("sequence", []),
        "governance_mode": governance.get("mode"),
        "law_manifest": law_manifest.get("mode"),
        "modules": manifest.get("modules", []),
        "files": files,
    }


def write_report(report: dict[str, Any]) -> None:
    out_dir = ROOT / "memory" / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "boot_report.json").open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boot", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    report = verify_payload()
    write_report(report)

    if args.smoke:
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
