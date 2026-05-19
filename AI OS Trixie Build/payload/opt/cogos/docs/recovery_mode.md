# Recovery Mode

CoGOS recovery mode provides a small repair surface when the normal operator
desktop is not enough.

Boot trigger:

```text
cogos.recovery=1
```

or create:

```sh
cogos-recovery enable
```

Commands:

```sh
cogos-recovery status
cogos-recovery verify
cogos-recovery snapshots
cogos-recovery backups
cogos-recovery rollback /opt/cogos/memory/snapshots/rollback-...
cogos-recovery restore-backup /opt/cogos/memory/backups/bundle-...
cogos-recovery reset-first-run
cogos-recovery disable
```

Recovery writes proof to `/opt/cogos/memory/logs/recovery_proof.json` and
append-only history to `/opt/cogos/memory/traces/recovery_history.jsonl`.

