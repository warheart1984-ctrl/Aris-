# forge Package

This folder contains the standalone Forge runtime/service package for the
nested `code/code` project.

It owns Forge request schemas, profiles, preflight checks, handler routing, and
service assembly.

## Owns

- Forge service assembly in [`service.py`](./service.py)
- runtime entrypoints in [`main.py`](./main.py)
- request/response schemas in [`schemas.py`](./schemas.py)
- environment and profile configuration in [`config.py`](./config.py) and
  [`profiles.py`](./profiles.py)
- handler and utility helpers in [`handlers/`](./handlers/) and [`utils/`](./utils/)

## Does Not Own

- the broader Evolving AI package in [`../evolving_ai/`](../evolving_ai/)
- Forge evaluation harnesses in [`../forge_eval/`](../forge_eval/)
- packaged release artifacts in [`../release/`](../release/)

## Main Files

- [`main.py`](./main.py)
  - service entrypoint
- [`service.py`](./service.py)
  - core runtime/service behavior
- [`schemas.py`](./schemas.py)
  - request and response models
- [`preflight.py`](./preflight.py)
  - startup/preflight checks

## Read Next

1. [../README.md](../README.md)
2. [../forge_eval/README.md](../forge_eval/README.md)
3. [../tests/README.md](../tests/README.md)
