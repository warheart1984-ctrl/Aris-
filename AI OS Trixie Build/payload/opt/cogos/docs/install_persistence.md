# CoGOS Install And Persistence

CoGOS live boots without touching disks by default. If a writable ext4 volume
labeled `COGOSDATA` is present, PID1 mounts it at `/var/lib/cogos` and
bind-mounts persistent state over:

- `/opt/cogos/config`
- `/opt/cogos/memory`
- `/opt/cogos/modules/local`

This keeps law/runtime files immutable from the ISO while letting operator
state, ledgers, backups, packages, profiles, and local modules survive reboot.

## Check Persistence

```sh
cogos-persist status
```

## Create A Data Partition

Use this only on a partition that may be formatted:

```sh
COGOS_CONFIRM_FORMAT=YES cogos-persist init-device /dev/sdXN
reboot
```

On next boot CoGOS mounts the partition automatically.

## Full Disk Install

Always inspect the plan first:

```sh
cogos-install plan --target /dev/sdX
cogos-install validate --target /dev/sdX
```

Apply mode erases the target disk and requires both `--yes` and an exact
target-name confirmation:

```sh
cogos-install apply --target /dev/sdX --yes --confirm-erase sdX
```

The installer creates EFI, root, and `COGOSDATA` partitions, copies the live
system, installs GRUB, and prepares the persistent CoGOS state store.

Useful options:

```sh
cogos-install plan --target /dev/sdX --json
cogos-install apply --target /dev/sdX --yes --confirm-erase sdX --hostname cogos --user operator
cogos-install apply --target /dev/sdX --yes --confirm-erase sdX --data-size 32GiB
cogos-install proof --json
```

The apply path refuses to run unless it is root, the target is a whole block
disk larger than 32 GiB, the target is not the currently booted root disk, and
the confirmation string matches the disk basename. Removable media requires
`--allow-removable`.
