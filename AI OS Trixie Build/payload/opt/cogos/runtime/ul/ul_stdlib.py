"""
ul_stdlib.py - UL standard library v0.1.

Small, deterministic helpers for normal CoGOS work: state, workspaces,
file plans, device snapshots, and user-facing notices. The stdlib is safe by
default: file helpers are constrained to CoGOS-owned memory/workspace roots.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional


STDLIB_VERSION = "0.1.0"


def _runtime_root() -> Path:
    try:
        from governance_invariant_engine import cogos_root

        return cogos_root()
    except Exception:
        return Path(__file__).resolve().parents[2]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")
    return value[:72] or "item"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _state_path() -> Path:
    root = _runtime_root()
    path = root / "memory" / "ul" / "stdlib_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"version": STDLIB_VERSION, "global": {}, "workspaces": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"version": STDLIB_VERSION, "global": {}, "workspaces": {}}


def _save_state(data: Dict[str, Any]) -> None:
    path = _state_path()
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _remember(key: str, value: Any, workspace: str = "") -> Dict[str, Any]:
    data = _load_state()
    bucket_name = _slug(workspace) if workspace else "global"
    if bucket_name == "global":
        bucket = data.setdefault("global", {})
    else:
        bucket = data.setdefault("workspaces", {}).setdefault(bucket_name, {})
    bucket[str(key)] = {"value": value, "updated_at": _now()}
    _save_state(data)
    return {"ok": True, "bucket": bucket_name, "key": str(key), "value": value}


def _recall(key: str = "", workspace: str = "") -> Any:
    data = _load_state()
    bucket_name = _slug(workspace) if workspace else "global"
    bucket = data.get("global", {}) if bucket_name == "global" else data.get("workspaces", {}).get(bucket_name, {})
    if key:
        row = bucket.get(str(key), {})
        return row.get("value")
    return {k: v.get("value") for k, v in bucket.items()}


def _safe_root_candidates() -> list[Path]:
    root = _runtime_root()
    return [
        root / "memory",
        root / "examples",
        root / "docs",
    ]


def _resolve_safe_path(raw: str, *, write: bool = False) -> Path:
    root = _runtime_root()
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = root / "memory" / "ul" / path
    resolved = path.resolve()
    safe_roots = [p.resolve() for p in _safe_root_candidates()]
    if not any(resolved == base or base in resolved.parents for base in safe_roots):
        raise PermissionError(f"UL stdlib path outside governed roots: {raw}")
    if write:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _read_text(path: str) -> str:
    return _resolve_safe_path(path).read_text(encoding="utf-8-sig")


def _write_text(path: str, text: str) -> Dict[str, Any]:
    target = _resolve_safe_path(path, write=True)
    target.write_text(str(text), encoding="utf-8")
    return {"ok": True, "path": str(target), "bytes": len(str(text).encode("utf-8"))}


def _workspace(name: str) -> Dict[str, Any]:
    try:
        from automatic_mode import AutomaticModeEngine

        return AutomaticModeEngine().create_workspace(str(name))
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def _organize_plan(source: str) -> Dict[str, Any]:
    try:
        from automatic_mode import AutomaticModeEngine

        return AutomaticModeEngine().organize_files(str(source), apply=False)
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def _auto_status() -> Dict[str, Any]:
    try:
        from automatic_mode import AutomaticModeEngine

        return AutomaticModeEngine().status()
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def _device_status() -> Dict[str, Any]:
    root = _runtime_root()
    snapshot = root / "memory" / "logs" / "hal_snapshot.json"
    if snapshot.exists():
        try:
            return json.loads(snapshot.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    try:
        from hal_service import observe_hal

        return observe_hal()
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "timestamp": _now()}


def _storage_status() -> Dict[str, Any]:
    try:
        from device_storage_manager import DeviceStorageManager

        return DeviceStorageManager().inventory()
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "timestamp": _now()}


def _notice(text: str) -> Dict[str, Any]:
    root = _runtime_root()
    path = root / "memory" / "ul" / "notices.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": _now(), "text": str(text)}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return {"ok": True, "notice": str(text), "path": str(path)}


def _summary(text: str) -> str:
    words = str(text).strip().split()
    if len(words) <= 18:
        return " ".join(words)
    return " ".join(words[:18]) + " ..."


def stdlib_manifest() -> Dict[str, Any]:
    return {
        "name": "UL stdlib",
        "version": STDLIB_VERSION,
        "groups": {
            "core": ["core.now", "core.slug", "core.json"],
            "fs": ["fs.read_text", "fs.write_text"],
            "state": ["state.remember", "state.recall"],
            "auto": ["auto.workspace", "auto.organize_plan", "auto.status"],
            "device": ["device.status"],
            "storage": ["storage.status"],
            "ui": ["ui.notice"],
            "agent": ["agent.summary"],
        },
    }


_CALLS: Dict[str, Callable[..., Any]] = {
    "core.now": _now,
    "core.slug": _slug,
    "core.json": _json,
    "fs.read_text": _read_text,
    "fs.write_text": _write_text,
    "state.remember": _remember,
    "state.recall": _recall,
    "auto.workspace": _workspace,
    "auto.organize_plan": _organize_plan,
    "auto.status": _auto_status,
    "device.status": _device_status,
    "storage.status": _storage_status,
    "net.status": _device_status,
    "ui.notice": _notice,
    "agent.summary": _summary,
}


_UL_BUILTINS: Dict[str, str] = {
    "ul_now": "core.now",
    "ul_slug": "core.slug",
    "ul_json": "core.json",
    "ul_read_text": "fs.read_text",
    "ul_write_text": "fs.write_text",
    "ul_remember": "state.remember",
    "ul_recall": "state.recall",
    "ul_workspace": "auto.workspace",
    "ul_organize_plan": "auto.organize_plan",
    "ul_status": "auto.status",
    "ul_device_status": "device.status",
    "ul_notice": "ui.notice",
    "ul_summary": "agent.summary",
}


def call_stdlib(name: str, args: Optional[Iterable[Any]] = None, context: Optional[Dict[str, Any]] = None) -> Any:
    del context
    fn = _CALLS.get(name)
    if not fn:
        raise KeyError(f"Unknown UL stdlib function: {name}")
    return fn(*(list(args or [])))


def stdlib_builtins() -> Dict[str, Callable[..., Any]]:
    builtins: Dict[str, Callable[..., Any]] = {}
    for ul_name, call_name in _UL_BUILTINS.items():
        builtins[ul_name] = lambda *args, _call_name=call_name: call_stdlib(_call_name, args)
    builtins["ul_stdlib_manifest"] = stdlib_manifest
    return builtins
