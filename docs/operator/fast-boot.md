# CoGOS v10 Fast Operator Boot

v10 makes CoGOS feel usable first, then visual when needed. The default boot
profile starts the governed runtime and daemon, but defers the dashboard so the
Hyper-V VM is not paying for a web UI during every boot.

## Boot Profile

Path inside the ISO:

```text
/opt/cogos/config/boot_profile.json
```

Default:

```json
{
  "profile": "operator_shell",
  "dashboard_autostart": false,
  "daemon_autostart": true,
  "boot_verify_autostart": true
}
```

## First Commands

```sh
cogos-operator
cogos-perf
cogos-proof
```

Use the dashboard only when you want the visual runtime view:

```sh
cogos-dashboard-start
```

Stop it when the VM feels heavy:

```sh
cogos-dashboard-stop
```

## Desktop

Puppy/Trixie desktop is still available. CoGOS v10 simply treats the operator
shell as the preferred first surface.

```sh
cogos-desktop-hint
```

## Hyper-V Defaults

The v10 helper scripts use:

- 4 virtual CPUs
- fixed 6GB startup memory
- dynamic memory disabled

Tune an existing VM from an elevated Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File "E:\project-infi\AI OS Trixie Build\scripts\tune_hyperv_vm.ps1"
```

## Governance

Governance stack unchanged from v9:

- Law Engine
- Sandboxed module execution
- Trait Identity Runtime
- Pattern Ledger
- Immune recommendations
- `cogos-proof`

