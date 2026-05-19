# First-Run Wizard

The first-run wizard turns a fresh CoGOS boot or install into a configured
operator environment.

It sets:

- hostname hint
- active operator profile
- default mode (`manual` or `automatic`)
- optional kid profile
- first Automatic workspace
- first-run proof at `/opt/cogos/memory/logs/first_run_proof.json`

## CLI

```sh
cogos-first-run status
cogos-first-run apply --hostname cogos --profile-id operator --display-name "Operator" --mode manual --workspace "Home Base"
cogos-first-run reset
```

The Control Center exposes the same setup path on the First Run panel.

