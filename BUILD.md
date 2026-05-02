# Build Guide

This repo now ships one supported desktop artifact from one supported runtime lane:

- source runtime: `evolving_ai/aris_runtime/`
- desktop entrypoint: `python -m evolving_ai.aris_runtime.desktop`
- Windows bundle artifact: `ARIS V2.exe`

## Supported Toolchain

- Python `3.12`
- `pip`
- desktop runtime dependencies: `.[desktop]`
- desktop build dependencies: `.[desktop-build]`

## Install

```powershell
cd "C:\Users\randj\Desktop\project infi\code\code"
py -3.12 -m pip install -e .[desktop-build]
```

## Prepare The UL Desktop Runtime

```powershell
.\prepare_aris_runtime_desktop_runtime.ps1
```

Equivalent direct command:

```powershell
py -3.12 -m evolving_ai.aris_runtime.desktop_runtime --prepare --with-build-tools
```

## Run The Desktop App

```powershell
.\run_aris_runtime_desktop.ps1
```

Equivalent direct command:

```powershell
py -3.12 -m evolving_ai.aris_runtime.desktop
```

## Build The Windows EXE

This is the only supported Windows build command:

```powershell
.\build_aris_runtime_desktop.ps1 -BuildTag current -Variant v2
```

Equivalent direct command:

```powershell
py -3.12 -m evolving_ai.aris_runtime.desktop_build --variant v2 --build-current
```

## Expected Output

```text
.runtime/aris_runtime_desktop_builds/windows/v2/current/dist/ARIS V2/ARIS V2.exe
```

## Health Checks

Runtime service:

```powershell
.\run_aris_runtime.ps1 --healthcheck
```

Desktop smokecheck:

```powershell
py -3.12 -m evolving_ai.aris_runtime.desktop --headless-smokecheck --no-workers
```

Packaged EXE smokecheck:

```powershell
& ".\\.runtime\\aris_runtime_desktop_builds\\windows\\v2\\current\\dist\\ARIS V2\\ARIS V2.exe" --headless-smokecheck --no-workers
```

## GitHub Build Lane

Cross-platform native bundle validation is defined in:

- `.github/workflows/aris-runtime-desktop-build.yml`

That workflow builds:

- Windows: `ARIS V2.exe`
- macOS: `ARIS V2.app`
- Linux: `dist/ARIS V2/`

## Release Rule

A repo change is not complete until:

- code exists
- verification exists
- logbook entry exists
- the logbook entry matches the change under 1001
