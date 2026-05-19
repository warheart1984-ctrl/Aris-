"""
cogos_backup.py — Governed backup export / cold restore (Phase 3).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from compute_tiers import ComputeTierEngine
from governance_invariant_engine import cogos_root


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _bundle_manifest(root: Path) -> Dict[str, Any]:
    files: List[Dict[str, str]] = []
    for f in sorted(root.rglob("*")):
        if f.is_file():
            rel = str(f.relative_to(root))
            files.append({"path": rel, "sha256": _sha256_file(f)})
    return {
        "version": "1.0",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": files,
        "file_count": len(files),
    }


BACKUP_COMPONENTS = (
    "law",
    "config",
    "memory/patterns",
    "memory/mesh",
    "memory/creative",
    "memory/operator",
    "memory/packages",
    "memory/logs/boot_report.json",
    "memory/logs/determinism_corridor.json",
    "memory/logs/hal_snapshot.json",
)


def export_backup(label: str = "operator", *, profile_id: str = "operator") -> Dict[str, Any]:
    tiers = ComputeTierEngine()
    check = tiers.check("backup.export", profile_id=profile_id)
    if not check.allowed:
        return {"ok": False, "error": check.reason}

    root = cogos_root()
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    dest = root / "memory" / "backups" / f"bundle-{ts}-{label}"
    dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    for rel in BACKUP_COMPONENTS:
        src = root / rel
        if not src.exists():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True)
            copied += sum(1 for _ in target.rglob("*") if _.is_file())
        else:
            shutil.copy2(src, target)
            copied += 1

    manifest = _bundle_manifest(dest)
    manifest["label"] = label
    manifest["lambda_anchor"] = "1ba1e8352ff43aec5203f9043bffc396d1969a1ef2999558f1c4bc9491b4c3a6"
    (dest / "BACKUP_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    log = root / "memory" / "traces" / "backup_history.jsonl"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": manifest["created_at"], "action": "export", "path": str(dest), "files": copied}) + "\n")

    return {"ok": True, "path": str(dest), "files": copied, "manifest": manifest}


def list_backups() -> List[Dict[str, Any]]:
    root = cogos_root() / "memory" / "backups"
    if not root.exists():
        return []
    out = []
    for p in sorted(root.glob("bundle-*"), reverse=True):
        mf = p / "BACKUP_MANIFEST.json"
        meta = json.loads(mf.read_text(encoding="utf-8-sig")) if mf.exists() else {}
        out.append({"path": str(p), "label": meta.get("label"), "created_at": meta.get("created_at"), "files": meta.get("file_count", 0)})
    return out


def import_backup(bundle_path: str, *, profile_id: str = "operator") -> Dict[str, Any]:
    tiers = ComputeTierEngine()
    check = tiers.check("backup.import", profile_id=profile_id)
    if not check.allowed:
        return {"ok": False, "error": check.reason}

    bundle = Path(bundle_path)
    mf = bundle / "BACKUP_MANIFEST.json"
    if not bundle.is_dir() or not mf.exists():
        return {"ok": False, "error": "invalid backup bundle"}

    root = cogos_root()
    pre = root / "memory" / "snapshots" / f"pre-import-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}"
    pre.mkdir(parents=True, exist_ok=True)
    for rel in ("law", "config"):
        src = root / rel
        if src.is_dir():
            shutil.copytree(src, pre / rel, dirs_exist_ok=True)
    restored = 0
    for item in bundle.rglob("*"):
        if not item.is_file() or item.name == "BACKUP_MANIFEST.json":
            continue
        rel = item.relative_to(bundle)
        if rel.parts[0] == "BACKUP_MANIFEST.json":
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        restored += 1

    log = root / "memory" / "traces" / "backup_history.jsonl"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": "import",
            "path": str(bundle),
            "files": restored,
        }) + "\n")

    return {"ok": True, "restored_files": restored, "bundle": str(bundle)}
