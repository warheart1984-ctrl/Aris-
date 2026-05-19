"""Smoke tests for Device + Storage Manager MVP."""

from __future__ import annotations

from pathlib import Path

from device_storage_manager import DeviceStorageManager
from governance_invariant_engine import cogos_root


def main() -> int:
    manager = DeviceStorageManager()
    status = manager.inventory()
    assert status["ok"]
    assert status["devices"]
    assert "storage" in status
    assert (cogos_root() / "memory" / "logs" / "device_storage.json").exists()

    plan = manager.plan_archive(str(cogos_root() / "memory"), label="smoke")
    assert plan["ok"]
    assert Path(plan["path"]).exists()
    assert not plan["detail"]["destructive"]

    mount = manager.plan_mount("/dev/sdz1", "/mnt/cogos-test")
    assert mount["ok"]
    assert mount["detail"]["requires_operator"]

    denied = manager.execute_mount("/not-dev/sdz1", "/mnt/cogos-test", yes=True, confirm="sdz1")
    assert not denied["ok"]
    assert "under /dev" in denied["reason"]

    denied_unmount = manager.execute_unmount("/tmp/not-cogos", yes=True, confirm="not-cogos")
    assert not denied_unmount["ok"]
    assert "CoGOS mountpoints" in denied_unmount["reason"]

    plans = manager.list_plans()
    assert len(plans) >= 2
    for row in (plan, mount):
        try:
            Path(row["path"]).unlink(missing_ok=True)
        except Exception:
            pass
    print("Device + Storage Manager smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
