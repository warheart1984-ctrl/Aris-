param(
  [string]$BuildTag = "current",
  [ValidateSet("demo", "v1", "v2")]
  [string]$Variant = "demo",
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$PassthroughArgs = @()
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if ($BuildTag -like "-*") {
  $PassthroughArgs = @($BuildTag) + $PassthroughArgs
  $BuildTag = "current"
}

$repoRoot = (Get-Location).Path
$desktopProjectRoot = if ($env:ARIS_DEMO_DESKTOP_BUILD_ROOT) {
  $env:ARIS_DEMO_DESKTOP_BUILD_ROOT
} else {
  Join-Path $repoRoot ".runtime\\aris_demo_desktop_builds"
}
$windowsRoot = Join-Path $desktopProjectRoot ("windows\\" + $Variant + "\\" + $BuildTag)
$distRoot = Join-Path $windowsRoot "dist"
$workRoot = Join-Path $windowsRoot "work"
$specRoot = Join-Path $windowsRoot "spec"

New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $workRoot | Out-Null
New-Item -ItemType Directory -Force -Path $specRoot | Out-Null

if (Test-Path ".\.runtime\ul_desktop_runtime\venv\Scripts\python.exe") {
  & ".\.runtime\ul_desktop_runtime\venv\Scripts\python.exe" -m evolving_ai.aris_demo.desktop_build --variant $Variant --build-current --distpath $distRoot --workpath $workRoot --specpath $specRoot @PassthroughArgs
  exit $LASTEXITCODE
}

if (Test-Path ".\.venv\Scripts\python.exe") {
  & ".\.venv\Scripts\python.exe" -m evolving_ai.aris_demo.desktop_build --variant $Variant --build-current --distpath $distRoot --workpath $workRoot --specpath $specRoot @PassthroughArgs
  exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
  python -m evolving_ai.aris_demo.desktop_build --variant $Variant --build-current --distpath $distRoot --workpath $workRoot --specpath $specRoot @PassthroughArgs
  exit $LASTEXITCODE
}

py -3 -m evolving_ai.aris_demo.desktop_build --variant $Variant --build-current --distpath $distRoot --workpath $workRoot --specpath $specRoot @PassthroughArgs
