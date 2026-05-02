# ARIS Runtime

This folder is the only supported desktop/runtime lane for packaged ARIS.

It owns:

- the governed desktop host
- runtime profile binding
- UL desktop runtime preparation
- desktop packaging
- shipping lane verification
- operator workspace surfaces

It does not own:

- archived demo history in `../../archive/demo/`
- the core ARIS law/runtime implementation in `../aris/`
- generated runtime state in `.forge_chat/` or `.runtime/`

## Main Entry Points

- `desktop.py`
  - desktop launcher
- `desktop_app.py`
  - PySide6 window and operator workspace
- `desktop_support.py`
  - desktop host bridge into the governed ARIS runtime
- `desktop_runtime.py`
  - UL-bound PySide6 runtime bootstrap
- `desktop_build.py`
  - PyInstaller build lane
- `shipping_lane.py`
  - packaged release verification
- `runtime.py`
  - runtime profile binding

## Build

See [../../BUILD.md](../../BUILD.md) for the supported ship path.
