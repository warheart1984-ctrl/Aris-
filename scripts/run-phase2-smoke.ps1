$ErrorActionPreference = "Stop"
$Payload = "E:\project-infi\AI OS Trixie Build\payload\opt\cogos"
$env:COGOS_ROOT = $Payload
$python = "E:\project-infi\AAIS-main\.runtime\python312-store-copy\python.exe"

& $python "$Payload\runtime\phase0_smoke.py"
& $python "$Payload\runtime\phase1_smoke.py"
& $python "$Payload\runtime\phase2_smoke.py"
