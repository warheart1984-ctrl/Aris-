$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$payload = Join-Path $root "payload\opt\cogos"
$required = @(
  "bin\cognitive_init",
  "bin\cogos_shell",
  "bin\cogos_boot.py",
  "bin\cogos_daemon.py",
  "bin\cogos_dashboard.py",
  "bin\cogos_operator_boot.py",
  "..\..\etc\init.d\90cogos",
  "..\..\usr\local\bin\cogos-status",
  "..\..\usr\local\bin\cogos-shell",
  "..\..\usr\local\bin\cogos-doctor",
  "..\..\usr\local\bin\cogos-daemon",
  "..\..\usr\local\bin\cogos-run",
  "..\..\usr\local\bin\cogos-task",
  "..\..\usr\local\bin\cogos-trace",
  "..\..\usr\local\bin\cogos-law",
  "..\..\usr\local\bin\cogos-admit",
  "..\..\usr\local\bin\cogos-snapshot",
  "..\..\usr\local\bin\cogos-reflect",
  "..\..\usr\local\bin\cogos-dashboard",
  "..\..\usr\local\bin\cogos-dashboard-start",
  "..\..\usr\local\bin\cogos-dashboard-stop",
  "..\..\usr\local\bin\cogos-desktop-hint",
  "..\..\usr\local\bin\cogos-verify-trace",
  "..\..\usr\local\bin\cogos-governance-test",
  "..\..\usr\local\bin\cogos-module",
  "..\..\usr\local\bin\cogos-traits",
  "..\..\usr\local\bin\cogos-patterns",
  "..\..\usr\local\bin\cogos-proof",
  "..\..\usr\local\bin\cogos-operator",
  "..\..\usr\local\bin\cogos-perf",
  "law\root_law.json",
  "law\boot_law.json",
  "law\governance_rules.json",
  "law\law_manifest.json",
  "config\runtime.json",
  "config\boot_profile.json",
  "config\module_manifest.json",
  "modules\registry.json",
  "modules\local\trace_analyzer\module.json",
  "modules\local\trace_analyzer\trace_analyzer.py",
  "modules\local\bad_mutator\module.json",
  "modules\local\bad_mutator\bad_mutator.py",
  "modules\local\invalid_output\module.json",
  "modules\local\invalid_output\invalid_output.py",
  "modules\local\slow_module\module.json",
  "modules\local\slow_module\slow_module.py",
  "docs\OPERATOR_HANDBOOK.md",
  "runtime\aais_unified.py",
  "runtime\aris_runtime.py",
  "runtime\ul_core.py",
  "runtime\forge_eval.py"
)

$missing = @()
foreach ($rel in $required) {
  $path = Join-Path $payload $rel
  if (-not (Test-Path -LiteralPath $path)) {
    $missing += $rel
  }
}

if ($missing.Count -gt 0) {
  Write-Error ("Missing payload files: " + ($missing -join ", "))
  exit 1
}

$matches = Get-ChildItem -LiteralPath $payload -Recurse -File |
  Select-String -Pattern "TrixiePup64-Wayland-2601-260502.iso" -ErrorAction SilentlyContinue
if ($matches) {
  Write-Error "Payload should not hard-code the source ISO name."
  exit 1
}

Get-ChildItem -LiteralPath $payload -Recurse -File |
  Select-Object FullName, Length |
  Format-Table -AutoSize

Write-Host "Payload verification passed."
