$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (Test-Path ".\.venv\Scripts\python.exe") {
  & ".\.venv\Scripts\python.exe" -m evolving_ai.aris_demo @args
  exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
  python -m evolving_ai.aris_demo @args
  exit $LASTEXITCODE
}

py -3 -m evolving_ai.aris_demo @args
