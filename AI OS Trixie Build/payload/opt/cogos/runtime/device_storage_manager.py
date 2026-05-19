"""Device + Storage Manager MVP.

Inventory first, action second. This module observes block devices,
mounts, filesystem capacity, removable-device hints, and writes governed
plans for mount/backup/archive operations without performing destructive
changes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional

from governance_invariant_engine import cogos_root


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def _int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _read_mounts() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    path = Path("/proc/mounts")
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        source, target, fstype, opts = parts[:4]
        rows.append({"source": source, "target": target, "fstype": fstype, "options": opts.split(",")})
    return rows


def _disk_usage(path: str) -> Dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
        percent = round((usage.used / usage.total) * 100, 2) if usage.total else 0
        return {"total": usage.total, "used": usage.used, "free": usage.free, "used_percent": percent}
    except Exception as exc:
        return {"error": str(exc)}


def _sys_block_inventory() -> List[Dict[str, Any]]:
    sys_block = Path("/sys/block")
    devices: List[Dict[str, Any]] = []
    if not sys_block.is_dir():
        return devices

    for item in sorted(sys_block.iterdir(), key=lambda p: p.name):
        name = item.name
        if name.startswith(("loop", "ram")):
            continue
        removable = _read(item / "removable", "0") == "1"
        size_sectors = _int(_read(item / "size", "0"))
        logical_block = _int(_read(item / "queue" / "logical_block_size", "512"), 512)
        size_bytes = size_sectors * logical_block
        model = _read(item / "device" / "model")
        vendor = _read(item / "device" / "vendor")
        transport = _read(item / "device" / "type")
        partitions = []
        for child in sorted(item.iterdir(), key=lambda p: p.name):
            if child.name.startswith(name) and child.name != name and (child / "size").exists():
                part_sectors = _int(_read(child / "size", "0"))
                partitions.append(
                    {
                        "name": child.name,
                        "path": f"/dev/{child.name}",
                        "size_bytes": part_sectors * logical_block,
                    }
                )
        devices.append(
            {
                "name": name,
                "path": f"/dev/{name}",
                "model": " ".join(x for x in (vendor, model) if x).strip() or name,
                "removable": removable,
                "transport": transport,
                "size_bytes": size_bytes,
                "partitions": partitions,
            }
        )
    return devices


def _fallback_inventory(root: Path) -> List[Dict[str, Any]]:
    usage = _disk_usage(str(root))
    return [
        {
            "name": "cogos-root",
            "path": str(root),
            "model": "CoGOS payload storage",
            "removable": False,
            "transport": "host",
            "size_bytes": usage.get("total", 0),
            "usage": usage,
            "partitions": [],
        }
    ]


def _mount_for_device(path: str, mounts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for mount in mounts:
        if mount.get("source") == path:
            return mount
    return None


def _mount_for_target(target: str, mounts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    target_path = str(Path(target))
    for mount in mounts:
        if mount.get("target") == target_path:
            return mount
    return None


def _classify(device: Dict[str, Any], mount: Optional[Dict[str, Any]]) -> str:
    if device.get("removable"):
        return "removable"
    if mount and mount.get("target") in ("/", "/home", "/var"):
        return "system"
    if str(device.get("path", "")).startswith(str(cogos_root())):
        return "payload"
    return "fixed"


@dataclass
class DeviceStorageManager:
    root: Path = cogos_root()

    def __post_init__(self) -> None:
        self.log_dir = self.root / "memory" / "logs"
        self.trace_dir = self.root / "memory" / "traces"
        self.plan_dir = self.root / "memory" / "storage" / "plans"
        self.proof_path = self.root / "memory" / "logs" / "device_storage_actions.jsonl"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.plan_dir.mkdir(parents=True, exist_ok=True)

    def inventory(self) -> Dict[str, Any]:
        mounts = _read_mounts()
        devices = _sys_block_inventory() or _fallback_inventory(self.root)
        enriched: List[Dict[str, Any]] = []
        for device in devices:
            mount = _mount_for_device(str(device.get("path")), mounts)
            row = dict(device)
            row["mount"] = mount
            row["class"] = _classify(row, mount)
            if mount:
                row["usage"] = _disk_usage(str(mount.get("target")))
            enriched.append(row)

        payload_usage = _disk_usage(str(self.root))
        memory_usage = _disk_usage(str(self.root / "memory"))
        report = {
            "ok": True,
            "timestamp": utc_now(),
            "root": str(self.root),
            "devices": enriched,
            "mounts": mounts[:80],
            "storage": {
                "payload": payload_usage,
                "memory": memory_usage,
                "plans": len(list(self.plan_dir.glob("*.json"))),
            },
            "warnings": self._warnings(enriched, payload_usage),
        }
        self.write_snapshot(report)
        return report

    def _warnings(self, devices: List[Dict[str, Any]], payload_usage: Dict[str, Any]) -> List[str]:
        warnings: List[str] = []
        if payload_usage.get("used_percent", 0) >= 90:
            warnings.append("payload storage above 90 percent")
        for device in devices:
            usage = device.get("usage") or {}
            if usage.get("used_percent", 0) >= 90:
                warnings.append(f"{device.get('name')} mounted storage above 90 percent")
        if not devices:
            warnings.append("no devices observed")
        return warnings

    def write_snapshot(self, report: Optional[Dict[str, Any]] = None) -> Path:
        data = report or self.inventory()
        path = self.log_dir / "device_storage.json"
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with (self.trace_dir / "device_storage.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": utc_now(), "kind": "inventory", "devices": len(data.get("devices", []))}) + "\n")
        return path

    def plan_mount(self, device_path: str, mountpoint: str = "") -> Dict[str, Any]:
        mountpoint = mountpoint or f"/mnt/cogos-{Path(device_path).name}"
        return self._write_plan(
            "mount",
            {
                "device": device_path,
                "mountpoint": mountpoint,
                "commands": [
                    f"mkdir -p {mountpoint}",
                    f"mount {device_path} {mountpoint}",
                ],
                "requires_operator": True,
                "destructive": False,
                "safe_execute": "cogos-device-storage mount DEVICE --mountpoint MOUNTPOINT --yes --confirm-mount DEVICE_BASENAME",
            },
        )

    def execute_mount(
        self,
        device_path: str,
        mountpoint: str = "",
        *,
        readonly: bool = True,
        yes: bool = False,
        confirm: str = "",
    ) -> Dict[str, Any]:
        device_path = str(device_path).strip()
        mountpoint = str(mountpoint or f"/mnt/cogos-{Path(device_path).name}").strip()
        check = self._validate_mount_request(device_path, mountpoint, yes=yes, confirm=confirm)
        if not check["ok"]:
            self._record_action("mount", check)
            return check
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            out = {"ok": False, "action": "mount", "reason": "mount requires root", "device": device_path, "mountpoint": mountpoint}
            self._record_action("mount", out)
            return out
        if not shutil.which("mount"):
            out = {"ok": False, "action": "mount", "reason": "mount command not found"}
            self._record_action("mount", out)
            return out

        Path(mountpoint).mkdir(parents=True, exist_ok=True)
        opts = "ro,nosuid,nodev,noexec" if readonly else "nosuid,nodev,noexec"
        cmd = ["mount", "-o", opts, device_path, mountpoint]
        completed = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        out = {
            "ok": completed.returncode == 0,
            "action": "mount",
            "device": device_path,
            "mountpoint": mountpoint,
            "readonly": readonly,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "timestamp": utc_now(),
        }
        self._record_action("mount", out)
        self.inventory()
        return out

    def execute_unmount(self, mountpoint: str, *, yes: bool = False, confirm: str = "") -> Dict[str, Any]:
        mountpoint = str(mountpoint).strip()
        check = self._validate_unmount_request(mountpoint, yes=yes, confirm=confirm)
        if not check["ok"]:
            self._record_action("unmount", check)
            return check
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            out = {"ok": False, "action": "unmount", "reason": "unmount requires root", "mountpoint": mountpoint}
            self._record_action("unmount", out)
            return out
        if not shutil.which("umount"):
            out = {"ok": False, "action": "unmount", "reason": "umount command not found"}
            self._record_action("unmount", out)
            return out

        completed = subprocess.run(["umount", mountpoint], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        out = {
            "ok": completed.returncode == 0,
            "action": "unmount",
            "mountpoint": mountpoint,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "timestamp": utc_now(),
        }
        self._record_action("unmount", out)
        self.inventory()
        return out

    def _validate_mount_request(self, device_path: str, mountpoint: str, *, yes: bool, confirm: str) -> Dict[str, Any]:
        if not yes:
            return {"ok": False, "action": "mount", "reason": "mount requires --yes"}
        if not device_path.startswith("/dev/"):
            return {"ok": False, "action": "mount", "reason": "device must be under /dev", "device": device_path}
        if confirm != Path(device_path).name:
            return {
                "ok": False,
                "action": "mount",
                "reason": f"--confirm-mount must equal {Path(device_path).name}",
                "device": device_path,
            }
        if not Path(device_path).exists():
            return {"ok": False, "action": "mount", "reason": "device does not exist", "device": device_path}
        if not Path(device_path).is_block_device():
            return {"ok": False, "action": "mount", "reason": "device is not a block device", "device": device_path}
        target = PurePosixPath(mountpoint)
        if not str(target).startswith("/"):
            return {"ok": False, "action": "mount", "reason": "mountpoint must be absolute", "mountpoint": mountpoint}
        allowed_prefixes = (PurePosixPath("/mnt"), PurePosixPath("/media"))
        if not any(target == prefix or prefix in target.parents for prefix in allowed_prefixes):
            return {"ok": False, "action": "mount", "reason": "mountpoint must be under /mnt or /media", "mountpoint": mountpoint}
        if not target.name.startswith("cogos-"):
            return {"ok": False, "action": "mount", "reason": "mountpoint basename must start with cogos-", "mountpoint": mountpoint}
        existing = _mount_for_device(device_path, _read_mounts())
        if existing:
            return {"ok": False, "action": "mount", "reason": "device already mounted", "mount": existing}
        target_existing = _mount_for_target(mountpoint, _read_mounts())
        if target_existing:
            return {"ok": False, "action": "mount", "reason": "mountpoint already mounted", "mount": target_existing}
        return {"ok": True}

    def _validate_unmount_request(self, mountpoint: str, *, yes: bool, confirm: str) -> Dict[str, Any]:
        if not yes:
            return {"ok": False, "action": "unmount", "reason": "unmount requires --yes"}
        target = PurePosixPath(mountpoint)
        if not str(target).startswith("/"):
            return {"ok": False, "action": "unmount", "reason": "mountpoint must be absolute", "mountpoint": mountpoint}
        if not (target.name.startswith("cogos-") and (PurePosixPath("/mnt") in target.parents or PurePosixPath("/media") in target.parents)):
            return {"ok": False, "action": "unmount", "reason": "only CoGOS mountpoints under /mnt or /media may be unmounted"}
        if confirm != target.name:
            return {"ok": False, "action": "unmount", "reason": f"--confirm-unmount must equal {target.name}"}
        mounted = _mount_for_target(mountpoint, _read_mounts())
        if not mounted:
            return {"ok": False, "action": "unmount", "reason": "mountpoint is not mounted", "mountpoint": mountpoint}
        return {"ok": True, "mount": mounted}

    def _record_action(self, kind: str, payload: Dict[str, Any]) -> None:
        row = {"ts": utc_now(), "kind": kind, **payload}
        self.proof_path.parent.mkdir(parents=True, exist_ok=True)
        with self.proof_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        with (self.trace_dir / "device_storage.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": row["ts"], "kind": f"execute.{kind}", "ok": bool(payload.get("ok")), "reason": payload.get("reason", "")}) + "\n")

    def plan_archive(self, source: str, label: str = "archive") -> Dict[str, Any]:
        target = self.root / "memory" / "storage" / f"{_safe_label(label)}-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
        return self._write_plan(
            "archive",
            {
                "source": source,
                "target": str(target),
                "commands": [f"tar -czf {target} {source}"],
                "requires_operator": False,
                "destructive": False,
            },
        )

    def plan_cleanup(self, target: str) -> Dict[str, Any]:
        return self._write_plan(
            "cleanup",
            {
                "target": target,
                "commands": [f"find {target} -type f -name '*.tmp' -print"],
                "requires_operator": True,
                "destructive": False,
                "note": "MVP cleanup only lists candidates; delete requires a later explicit governed action.",
            },
        )

    def _write_plan(self, kind: str, detail: Dict[str, Any]) -> Dict[str, Any]:
        plan_id = f"{kind}-{time.strftime('%Y%m%d-%H%M%S')}"
        payload = {
            "ok": True,
            "id": plan_id,
            "kind": kind,
            "timestamp": utc_now(),
            "detail": detail,
            "status": "planned",
        }
        path = self.plan_dir / f"{plan_id}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["path"] = str(path)
        with (self.trace_dir / "device_storage.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": utc_now(), "kind": f"plan.{kind}", "plan_id": plan_id}) + "\n")
        return payload

    def list_plans(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = []
        for path in sorted(self.plan_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            row = _read_json(path, {})
            if row:
                row["path"] = str(path)
                rows.append(row)
        return rows


def _safe_label(value: str) -> str:
    import re

    label = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value).strip()).strip("-")
    return label[:64] or "archive"


def device_storage_status() -> Dict[str, Any]:
    return DeviceStorageManager().inventory()
