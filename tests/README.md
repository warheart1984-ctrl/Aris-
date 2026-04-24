# tests

This folder contains the automated verification layer for the nested
`code/code` project.

It owns coverage for the app shell, ARIS governance/runtime behavior, desktop
host lanes, shipping rules, and supporting package logic.

## Owns

- backend and package regression tests
- ARIS governance, memory, and law-spine verification
- desktop runtime, shipping lane, and workspace registry tests
- application and model-switchboard coverage

## Does Not Own

- source implementation in [`../evolving_ai/`](../evolving_ai/)
- Forge runtime implementation in [`../forge/`](../forge/)
- release artifacts in [`../release/`](../release/)

## Key Test Groups

- [`test_ai_app.py`](./test_ai_app.py)
  - app shell and broader runtime behavior
- [`test_aris_governance.py`](./test_aris_governance.py)
  - ARIS governance and law behavior
- [`test_aris_demo_desktop_runtime.py`](./test_aris_demo_desktop_runtime.py)
  - desktop runtime preparation and support
- [`test_aris_demo_shipping_lane.py`](./test_aris_demo_shipping_lane.py)
  - packaging/shipping completion checks
- [`test_law_spine.py`](./test_law_spine.py)
  - law-spine behavior

## Main Command

```bash
python -m pytest -q
```

## Read Next

1. [../README.md](../README.md)
2. [../evolving_ai/README.md](../evolving_ai/README.md)
3. [../forge/README.md](../forge/README.md)
4. [../release/README.md](../release/README.md)
