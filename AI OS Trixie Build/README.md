# Project Infi / ARIS Trixie Build

This directory is the build kit for turning the downloaded Trixie ISO into a
Project Infi / ARIS cognitive OS developer platform.

It follows the clean AAIS and ARIS planning docs:

- AAIS supplies authority, governance, module admission, memory, mission, and
  capability boundaries.
- ARIS supplies the governed runtime cycle, UL/VOSS execution model, trace
  discipline, and build/runtime separation.
- The Trixie image supplies the bootable Linux substrate, drivers, kernel,
  syscalls, and base filesystem.

## What Is Staged

- `payload/opt/cogos/bin/cognitive_init`: PID 1 entrypoint for the prototype.
- `payload/opt/cogos/bin/cogos_boot.py`: governed boot verification harness.
- `payload/opt/cogos/bin/cogos_operator_boot.py`: v10 fast operator surface.
- `payload/opt/cogos/bin/cogos_shell`: minimal operator shell.
- `payload/opt/cogos/runtime`: current AAIS/ARIS runtime files from this
  workspace.
- `payload/opt/cogos/law`: root law, boot law, governance rules, and the clean
  planning docs.
- `scripts/build_trixie_cogos.sh`: Linux remaster script.
- `scripts/verify_payload.ps1`: Windows-side payload sanity check.

## Build On Linux Or WSL

Install the required tools in the Linux environment:

```bash
sudo apt-get update
sudo apt-get install -y squashfs-tools xorriso rsync
```

Run the build from this directory:

```bash
bash scripts/build_trixie_cogos.sh "/mnt/e/project-infi/TrixiePup64-Wayland-2601-260502.iso"
```

If building from WSL against a Windows-mounted workspace, use a native Linux
temporary work directory so Linux symlinks, hardlinks, and device metadata are
preserved during SquashFS extraction:

```bash
sudo COGOS_WORK=/tmp/project-infi-cogos-build bash scripts/build_trixie_cogos.sh "/mnt/e/project-infi/TrixiePup64-Wayland-2601-260502.iso"
```

Expected output:

```text
output/project-infi-aris-trixie-full-os-v10.iso
```

## Boot Behavior

The full OS build preserves the original TrixiePup init path and installs
Project Infi / ARIS as a normal startup layer through `/etc/init.d/90cogos`.
The prototype `/opt/cogos/bin/cognitive_init` remains available in the image,
but it is not used as PID 1 by the full OS build.

On boot:

1. TrixiePup boots normally through its native init and service scripts.
2. `/etc/init.d/90cogos` starts after the base OS services.
3. CoGOS reads `/opt/cogos/config/boot_profile.json`.
4. CoGOS launches boot verification and the daemon in fast operator mode.
5. CoGOS defers the dashboard unless `dashboard_autostart` is enabled.
6. CoGOS writes `/opt/cogos/memory/logs/boot_report.json`.

Inside the running OS, use:

```sh
cogos-status
cogos-operator
cogos-perf
cogos-shell
cogos-daemon --status
cogos-run "record this test cycle"
cogos-task "queue this for the daemon"
cogos-trace
cogos-trace --explain latest
cogos-trace --replay latest
cogos-law task.execute task.execute memory.append
cogos-admit /opt/cogos/bin/cogos_daemon.py
cogos-snapshot create baseline
cogos-reflect "proposal text"
cogos-verify-trace latest
cogos-governance-test
cogos-dashboard
cogos-dashboard-start
cogos-dashboard-stop
cogos-desktop-hint
cogos-module admit /opt/cogos/modules/local/trace_analyzer
cogos-module list
cogos-module verify trace_analyzer
cogos-module run trace_analyzer
cogos-traits list
cogos-traits audit trace_analyzer
cogos-traits prove
cogos-patterns ingest
cogos-patterns list
cogos-patterns fame
cogos-patterns shame
cogos-patterns immune
cogos-patterns guidance
cogos-patterns prove
cogos-module admit /opt/cogos/modules/local/bad_mutator
cogos-module admit /opt/cogos/modules/local/invalid_output
cogos-module run invalid_output
cogos-module admit /opt/cogos/modules/local/slow_module
cogos-module run slow_module
cogos-module quarantine trace_analyzer "operator review"
cogos-proof
cogos-doctor
```

The local dashboard is now on-demand by default to keep Hyper-V responsive:

```text
cogos-dashboard-start
http://localhost:8080
cogos-dashboard-stop
```

v7 adds sandboxed governed module execution. A module run is admitted only
after law, registry, trait ledger, hash integrity, and sandbox policy checks.
The module runs as a bounded local subprocess with JSON stdin/stdout and writes
execution proof to `/opt/cogos/memory/modules/executions.jsonl`.

v8 adds Trait Identity Runtime. Every module run emits identity evidence,
updates `/opt/cogos/memory/modules/identity_state.json`, records drift in
`/opt/cogos/memory/modules/drift.jsonl`, and can request governed quarantine
after high-severity or repeated trait violations.

v9 adds Pattern Ledger + Immune Runtime. Runtime evidence is classified into
Fame, Shame, immune recommendations, and guidance candidates under
`/opt/cogos/memory/patterns`.

v10 adds Fast Operator Boot. The default path is `operator_shell`: boot proof
and daemon are started, while dashboard and heavier desktop work are operator
choice. Hyper-V helper scripts now target the v10 ISO with 4 CPUs and fixed
6GB startup memory.

## Safety Notes

The source ISO is never modified. The script creates a new ISO in `output/`.

If the payload fails verification inside the image, boot falls back to a
maintenance shell instead of pretending the governed runtime is ready.
