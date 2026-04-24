param(
  [string]$BuildTag = "current",
  [string]$ReleaseRoot = "",
  [switch]$Zip
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$repoRoot = (Get-Location).Path
if ([string]::IsNullOrWhiteSpace($ReleaseRoot)) {
  $ReleaseRoot = Split-Path $repoRoot -Parent
}

$artifacts = @{
  demo = "ARIS Demo"
  v1   = "ARIS Demo V1"
  v2   = "ARIS Demo V2"
}

foreach ($variant in @("demo", "v1", "v2")) {
  & "$PSScriptRoot\build_aris_demo_desktop.ps1" -BuildTag $BuildTag -Variant $variant
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }

  $artifact = $artifacts[$variant]
  $distFolder = Join-Path $repoRoot (".runtime\aris_demo_desktop_builds\windows\" + $variant + "\" + $BuildTag + "\dist\" + $artifact)
  if (-not (Test-Path $distFolder)) {
    throw "Expected built artifact folder missing: $distFolder"
  }

  $releaseFolder = Join-Path $ReleaseRoot $artifact
  if (Test-Path $releaseFolder) {
    Remove-Item -Recurse -Force $releaseFolder
  }
  Copy-Item -Recurse -Force $distFolder $releaseFolder

  if ($Zip) {
    $zipPath = Join-Path $ReleaseRoot ($artifact + ".zip")
    if (Test-Path $zipPath) {
      Remove-Item -Force $zipPath
    }
    Compress-Archive -Path $releaseFolder -DestinationPath $zipPath -Force
  }
}
