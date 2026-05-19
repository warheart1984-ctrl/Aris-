# Device + Storage Manager MVP

The Device + Storage Manager gives CoGOS a governed view of disks, mounts,
capacity, removable media hints, and storage action plans.

The MVP observes and plans. It does not format disks, delete files, or mount
devices automatically.

## Commands

```sh
cogos-device-storage status
cogos-device-storage plans
cogos-device-storage plan-mount /dev/sdb1 --mountpoint /mnt/cogos-usb
cogos-device-storage mount /dev/sdb1 --mountpoint /mnt/cogos-usb --yes --confirm-mount sdb1
cogos-device-storage unmount /mnt/cogos-usb --yes --confirm-unmount cogos-usb
cogos-device-storage plan-archive /opt/cogos/memory --label before-update
cogos-device-storage plan-cleanup /opt/cogos/memory
```

## Outputs

- Snapshot: `/opt/cogos/memory/logs/device_storage.json`
- Trace: `/opt/cogos/memory/traces/device_storage.jsonl`
- Plans: `/opt/cogos/memory/storage/plans/*.json`
- Mount/unmount proofs: `/opt/cogos/memory/logs/device_storage_actions.jsonl`

## MVP Policy

- Inventory is allowed in automatic mode.
- Plans are non-destructive JSON records.
- Mount execution is read-only by default and requires root, `--yes`, and
  `--confirm-mount` matching the device basename.
- Unmount execution only operates on CoGOS mountpoints under `/mnt` or
  `/media` whose basename starts with `cogos-`.
- Cleanup plans list candidates only; deletion is intentionally out of scope.
