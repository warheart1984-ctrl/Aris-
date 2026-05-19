#!/usr/bin/env python3
"""Governed update channel with rollback snapshots (Phase 1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
RUNTIME = ROOT / "runtime"
for p in (RUNTIME, RUNTIME / "ul", RUNTIME / "voss"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from manifest_signing import verify_manifest_file  # noqa: E402


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _log_update(action: str, detail: Dict[str, Any]) -> None:
    log = ROOT / "memory" / "traces" / "update_history.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "action": action, **detail}
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def create_rollback_point(label: str = "manual") -> Dict[str, Any]:
    cfg = json.loads((ROOT / "config" / "update_channel.json").read_text(encoding="utf-8-sig"))
    snap_dir = Path(cfg.get("snapshots_dir", str(ROOT / "memory" / "snapshots")))
    snap_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    name = f"rollback-{ts}-{label}"
    dest = snap_dir / name
    dest.mkdir(parents=True)

    manifest: Dict[str, Any] = {"label": label, "ts": ts, "files": []}
    for rel in ("law", "config"):
        src = ROOT / rel
        if not src.is_dir():
            continue
        target = dest / rel
        shutil.copytree(src, target, dirs_exist_ok=True)
        for f in target.rglob("*"):
            if f.is_file():
                manifest["files"].append({"path": str(f.relative_to(dest)), "sha256": _sha256(f)})

    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _log_update("snapshot_create", {"path": str(dest), "files": len(manifest["files"])})
    _rotate_snapshots(snap_dir, int(cfg.get("rollback_points_max", 8)))
    return {"ok": True, "snapshot": str(dest), "files": len(manifest["files"])}


def _rotate_snapshots(snap_dir: Path, keep: int) -> None:
    snaps = sorted(snap_dir.glob("rollback-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in snaps[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def list_rollback_points() -> List[Dict[str, Any]]:
    snap_dir = ROOT / "memory" / "snapshots"
    out = []
    for p in sorted(snap_dir.glob("rollback-*"), reverse=True):
        mf = p / "manifest.json"
        meta = json.loads(mf.read_text(encoding="utf-8-sig")) if mf.exists() else {}
        out.append({"path": str(p), "label": meta.get("label"), "ts": meta.get("ts"), "files": len(meta.get("files", []))})
    return out


def apply_rollback(snapshot_path: str) -> Dict[str, Any]:
    snap = Path(snapshot_path)
    if not snap.is_dir():
        return {"ok": False, "error": "snapshot not found"}
    create_rollback_point("pre-restore")
    for rel in ("law", "config"):
        src = snap / rel
        if not src.is_dir():
            continue
        dest = ROOT / rel
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
    _log_update("rollback_apply", {"snapshot": str(snap)})
    return {"ok": True, "restored_from": str(snap)}


def show_manifest() -> Dict[str, Any]:
    mf = ROOT / "config" / "release_manifest.json"
    if mf.exists():
        verification = verify_manifest_file(mf)
        if not verification.get("ok"):
            return {"ok": False, "error": "release manifest signature verification failed", "verification": verification}
        return json.loads(mf.read_text(encoding="utf-8-sig"))
    return {
        "version": "12.0.0-phase1",
        "channel": "stable",
        "components": ["cogos_runtime", "governance_invariant_engine", "hal_service", "phase1_panels"],
        "note": "Local manifest — extend for signed OTA later",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CoGOS governed update")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("manifest", help="Show release manifest")
    sub.add_parser("verify", help="Verify signed update/release manifests")
    snap = sub.add_parser("snapshot", help="Create rollback point")
    snap.add_argument("--label", default="manual")
    sub.add_parser("list", help="List rollback points")
    rb = sub.add_parser("rollback", help="Restore law+config from snapshot")
    rb.add_argument("path")

    args = parser.parse_args()
    if args.cmd == "manifest":
        print(json.dumps(show_manifest(), indent=2))
        return 0
    if args.cmd == "verify":
        checks = [
            verify_manifest_file(ROOT / "config" / "release_manifest.json"),
            verify_manifest_file(ROOT / "config" / "update_channel.json"),
        ]
        out = {"ok": all(c.get("ok") for c in checks), "checks": checks}
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] else 1
    if args.cmd == "snapshot":
        print(json.dumps(create_rollback_point(args.label), indent=2))
        return 0
    if args.cmd == "list":
        print(json.dumps(list_rollback_points(), indent=2))
        return 0
    if args.cmd == "rollback":
        print(json.dumps(apply_rollback(args.path), indent=2))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
