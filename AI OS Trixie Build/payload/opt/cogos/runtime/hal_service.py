"""
hal_service.py — HAL daemon skeleton: disks, hotplug hints, host observation.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from governance_invariant_engine import cogos_root

_HAL_PARENT = Path(__file__).resolve().parent
if str(_HAL_PARENT) not in sys.path:
    sys.path.insert(0, str(_HAL_PARENT))

from net_gre import NetFlow, NetGRE  # noqa: E402


def _observe_disks() -> List[Dict[str, Any]]:
    disks: List[Dict[str, Any]] = []
    by_id = Path("/dev/disk/by-id")
    if by_id.is_dir():
        for entry in sorted(by_id.iterdir())[:24]:
            if entry.is_symlink():
                disks.append({"id": entry.name, "target": os.readlink(entry)})
    else:
        for letter in "abcdef":
            p = Path(f"/sys/block/sd{letter}")
            if p.is_dir():
                disks.append({"block": p.name, "removable": (p / "removable").read_text().strip()
                              if (p / "removable").exists() else "?"})
    return disks


def _observe_net_interfaces() -> List[Dict[str, Any]]:
    ifaces: List[Dict[str, Any]] = []
    net = Path("/sys/class/net")
    if not net.is_dir():
        return ifaces
    for iface in sorted(net.iterdir()):
        if not iface.is_dir():
            continue
        ifaces.append({
            "name": iface.name,
            "operstate": (iface / "operstate").read_text().strip() if (iface / "operstate").exists() else "",
        })
    return ifaces


def observe_hal(*, profile_id: str = "operator") -> Dict[str, Any]:
    host_state: Dict[str, Any] = {}
    try:
        from host_adapters.linux_cinnamon_adapter import (
            observe_meta_registers,
            observe_state_registers,
        )

        host_state = {
            "state_registers": observe_state_registers(),
            "meta_registers": observe_meta_registers(),
        }
    except Exception as exc:
        host_state = {"error": str(exc)}

    net_gre = NetGRE()
    # Sample policy ping — loopback health check metadata only
    ping = net_gre.evaluate(
        NetFlow("outbound", "tcp", "127.0.0.1", 443, module_id="HAL", profile_id=profile_id)
    )

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "disks": _observe_disks(),
        "net_interfaces": _observe_net_interfaces(),
        "host": host_state,
        "net_gre_sample": {"allowed": ping.allowed, "violations": ping.violations},
        "device_storage": _observe_device_storage(),
    }


def _observe_device_storage() -> Dict[str, Any]:
    try:
        from device_storage_manager import DeviceStorageManager

        data = DeviceStorageManager().inventory()
        return {
            "ok": bool(data.get("ok")),
            "devices": len(data.get("devices", [])),
            "warnings": data.get("warnings", []),
            "storage": data.get("storage", {}),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def write_hal_snapshot(data: Optional[Dict[str, Any]] = None) -> Path:
    root = cogos_root()
    out = root / "memory" / "logs" / "hal_snapshot.json"
    payload = data or observe_hal()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    jsonl = root / "memory" / "traces" / "hal_observations.jsonl"
    with jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")
    return out


def run_daemon(interval: float = 30.0, once: bool = False) -> None:
    while True:
        write_hal_snapshot()
        if once:
            break
        time.sleep(interval)
