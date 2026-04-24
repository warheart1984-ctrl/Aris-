# forge_eval Package

This folder contains Forge evaluation helpers and sandbox support.

It owns evaluator modules, sandbox helpers, and the lighter-weight evaluation
service layer used to measure or exercise Forge behavior.

## Owns

- evaluator modules in [`evaluators/`](./evaluators/)
- sandbox support in [`sandbox/`](./sandbox/)
- evaluation service assembly in [`service.py`](./service.py)
- evaluation schemas in [`schemas.py`](./schemas.py)

## Does Not Own

- the live Forge service package in [`../forge/`](../forge/)
- the broader application/runtime package in [`../evolving_ai/`](../evolving_ai/)
- release artifacts in [`../release/`](../release/)

## Main Files

- [`main.py`](./main.py)
  - evaluation entrypoint
- [`service.py`](./service.py)
  - evaluation service behavior
- [`schemas.py`](./schemas.py)
  - evaluation data models

## Read Next

1. [../forge/README.md](../forge/README.md)
2. [../tests/README.md](../tests/README.md)
3. [../README.md](../README.md)
