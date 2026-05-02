$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (Test-Path ".\.runtime\ul_desktop_runtime\venv\Scripts\python.exe") {
  & ".\.runtime\ul_desktop_runtime\venv\Scripts\python.exe" -m evolving_ai.aris_runtime.desktop @args
  exit $LASTEXITCODE
}

if (Test-Path ".\.venv\Scripts\python.exe") {
  & ".\.venv\Scripts\python.exe" -m evolving_ai.aris_runtime.desktop @args
  exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
  python -m evolving_ai.aris_runtime.desktop @args
  exit $LASTEXITCODE
}

py -3 -m evolving_ai.aris_runtime.desktop @args
