# evolving_ai Package

This folder contains the main Python package for the nested `code/code`
project.

It owns the evolutionary framework, the local-first AI app shell, the ARIS law
and runtime modules, and the ARIS desktop/demo package entrypoints.

## Owns

- package entrypoints declared in [`../pyproject.toml`](../pyproject.toml)
- the evolutionary engine and task framework
- the app/server layer in [`app/`](./app/)
- the ARIS runtime and law modules in [`aris/`](./aris/)
- the ARIS demo desktop and shipping lanes in [`aris_demo/`](./aris_demo/)

## Does Not Own

- the standalone Forge service package in [`../forge/`](../forge/)
- Forge evaluation helpers in [`../forge_eval/`](../forge_eval/)
- built release artifacts in [`../release/`](../release/)
- test authority in [`../tests/`](../tests/)

## Main Folders

- [`app/`](./app/)
  - local-first chat/app server, execution backends, review, files, and UI
- [`aris/`](./aris/)
  - ARIS runtime, law, shield, integrity, memory, and support modules
- [`aris_demo/`](./aris_demo/)
  - desktop host, runtime prep, shipping lane, and workspace demo logic
- [`evolvingai/`](./evolvingai/)
  - additional package helpers kept under the same distribution root

## Main Files

- [`cli.py`](./cli.py)
  - package CLI entrypoint
- [`engine.py`](./engine.py)
  - evolutionary training loop
- [`advanced_code_agents.py`](./advanced_code_agents.py)
  - code-agent benchmark and synthesis logic
- [`tasks.py`](./tasks.py)
  - pluggable evaluation tasks
- [`config.py`](./config.py)
  - core experiment configuration

## Read Next

1. [../README.md](../README.md)
2. [./app/server.py](./app/server.py)
3. [./aris/launcher.py](./aris/launcher.py)
4. [./aris_demo/desktop.py](./aris_demo/desktop.py)
5. [../tests/README.md](../tests/README.md)
