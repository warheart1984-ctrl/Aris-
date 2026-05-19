# Phase 0 smoke — set COGOS_ROOT to the CoGOS payload and run tests.
$ErrorActionPreference = "Stop"
$Payload = "E:\project-infi\AI OS Trixie Build\payload\opt\cogos"
$env:COGOS_ROOT = $Payload

$python = @(
    "E:\project-infi\AAIS-main\.runtime\python312-store-copy\python.exe",
    "python3",
    "python"
) | Where-Object { Test-Path $_ -or $_ -match '^python' } | Select-Object -First 1

if (-not $python) {
    Write-Error "No Python found. Install Python 3.12+ or fix AAIS-main venv path."
}

& $python "$Payload\runtime\phase0_smoke.py"
& $python "$Payload\bin\cogos_boot.py" --smoke
