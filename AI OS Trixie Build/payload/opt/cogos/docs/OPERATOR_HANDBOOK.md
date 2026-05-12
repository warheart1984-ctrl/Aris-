# CoGOS Operator Handbook

## Boot Flow

1. Boot the v10 ISO in Hyper-V.
2. Wait for Puppy/Trixie to finish loading.
3. Open a terminal.
4. Run `cogos-operator` for the fast operator surface.
5. Run `cogos-status` to confirm the boot report exists.
6. Start the dashboard only when needed with `cogos-dashboard-start`.

## Known-Good Proof Sequence

```sh
cogos-operator
cogos-perf
cogos-daemon --verify-laws
cogos-run "operator proof cycle"
cogos-verify-trace latest
cogos-governance-test
cogos-proof
```

All commands should report `ok: true` or deterministic verification.

## V10 Fast Operator Boot

v10 is tuned for responsiveness in Hyper-V. The boot profile is stored at
`/opt/cogos/config/boot_profile.json`. The default profile starts boot
verification and the daemon, but defers the web dashboard.

Fast mode commands:

```sh
cogos-operator
cogos-perf
cogos-dashboard-start
cogos-dashboard-stop
cogos-desktop-hint
```

Known-good v10 sequence:

```sh
cogos-operator
cogos-daemon --verify-laws
cogos-module admit /opt/cogos/modules/local/trace_analyzer
cogos-module run trace_analyzer
cogos-traits prove
cogos-patterns ingest
cogos-patterns prove
cogos-proof
```

Lag recovery:

```sh
cogos-dashboard-stop
cogos-perf
cat /var/log/cogos-service.log
```

From Windows, tune an existing Hyper-V VM with fixed 6GB memory and 4 CPUs:

```powershell
powershell -ExecutionPolicy Bypass -File "E:\project-infi\AI OS Trixie Build\scripts\tune_hyperv_vm.ps1"
```

## Module Admission Workflow

Admit the known-good sample module:

```sh
cogos-module admit /opt/cogos/modules/local/trace_analyzer
cogos-module list
cogos-module verify trace_analyzer
cogos-module inspect trace_analyzer
cogos-module run trace_analyzer
```

Reject-path test:

```sh
cogos-module admit /opt/cogos/modules/local/bad_mutator
```

This should be denied because it combines `readonly` with `memory.write`.

## V7 Sandboxed Module Workflow

Known-good v7 proof sequence:

```sh
cogos-daemon --verify-laws
cogos-module admit /opt/cogos/modules/local/trace_analyzer
cogos-module verify trace_analyzer
cogos-module run trace_analyzer
cogos-proof
```

Every `cogos-module run` request goes through law, registry, trait ledger,
hash verification, sandbox policy, bounded subprocess execution, JSON output
validation, and trace recording.

Sandbox failures are governed results:

- `module is not admitted`: admit the module first.
- `module hash changed after admission`: re-admit after reviewing the change.
- `module status is quarantined`: inspect and re-admit only after review.
- `sandbox denied capability`: remove forbidden capabilities or change the law.
- `module stdout is not valid JSON`: fix the module output contract.
- `module execution timed out`: reduce work or adjust the runtime timeout.

Quarantine a module:

```sh
cogos-module quarantine trace_analyzer "operator review"
```

Re-admit the module to restore execution after the issue is resolved.

## V8 Trait Identity Runtime

Known-good v8 proof sequence:

```sh
cogos-daemon --verify-laws
cogos-module admit /opt/cogos/modules/local/trace_analyzer
cogos-module run trace_analyzer
cogos-traits list
cogos-traits audit trace_analyzer
cogos-traits prove
cogos-proof
```

Every module run emits trait evidence and updates identity state. The runtime
observes first, warns on drift, and requests governed quarantine only for
high-severity or repeated violations.

Drift severity:

- S1: local note.
- S2: warning evidence.
- S3: drift evidence.
- S4: quarantine-eligible governance violation.
- S5: critical quarantine-eligible violation.

Trait recovery commands:

```sh
cogos-traits inspect trace_analyzer
cogos-traits events trace_analyzer
cogos-traits audit trace_analyzer
cogos-module admit /opt/cogos/modules/local/trace_analyzer
```

## V9 Pattern Ledger + Immune Runtime

Known-good v9 proof sequence:

```sh
cogos-daemon --verify-laws
cogos-module admit /opt/cogos/modules/local/trace_analyzer
cogos-module run trace_analyzer
cogos-module run trace_analyzer
cogos-module run trace_analyzer
cogos-patterns ingest
cogos-patterns list
cogos-patterns fame
cogos-patterns prove
cogos-proof
```

The Pattern Ledger classifies runtime evidence into Fame, Shame, immune
recommendations, and guidance candidates. Severe or repeated failures can
produce immune recommendations, while repeatable success can become guidance
eligible.

Pattern review commands:

```sh
cogos-patterns ingest
cogos-patterns shame
cogos-patterns immune
cogos-patterns guidance
cogos-patterns inspect <pattern_id>
```

## Dashboard

The dashboard shows daemon health, law decisions, module registry, trait ledger,
trace verification, sandbox status, recent module runs, sandbox denials,
identity state, drift score, trait warnings, quarantined modules, snapshots,
reflections, Pattern Ledger, Hall of Fame, Hall of Shame, immune recommendations,
guidance candidates, boot profile, performance status, and recovery hints.

```text
cogos-dashboard-start
http://localhost:8080
```

## Recovery Commands

```sh
cogos-doctor
cat /var/log/cogos-service.log
cogos-daemon --verify-laws
cogos-trace --explain latest
cogos-trace --replay latest
cogos-module verify trace_analyzer
cogos-module run trace_analyzer
cogos-traits audit trace_analyzer
cogos-traits prove
cogos-patterns ingest
cogos-patterns prove
cogos-proof
```

## Common Errors

- No boot report: run `/etc/init.d/90cogos start`.
- No dashboard: run `cogos-dashboard-start` and reopen `http://localhost:8080`.
- Laggy VM: run `cogos-dashboard-stop`, then `cogos-perf`.
- Module rejected: inspect `cogos-module registry` and check trait/capability conflicts.
- Law integrity false: the law files changed after the manifest was generated.
