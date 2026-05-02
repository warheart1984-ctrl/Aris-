# Demo Archive

This folder quarantines retired demo-era ARIS assets instead of deleting them blindly.

It is kept for:

- architectural lineage
- edge-case recovery
- UI and workflow evidence
- comparison against the live `evolving_ai/aris_runtime/` lane

## Contents

- `source_snapshot/`
  - restored source snapshot of the retired `evolving_ai/aris_demo/` package and its helper scripts
- `prototypes/`
  - archived prototype-only UI surface that is no longer part of the shipped runtime
- `tests/`
  - demo-only contract tests that are no longer part of the active verification lane

## Rule

Nothing in this folder is part of the supported runtime path.

The only supported desktop runtime now lives in:

- `evolving_ai/aris_runtime/`

The only supported packaged Windows artifact is:

- `ARIS V2.exe`
