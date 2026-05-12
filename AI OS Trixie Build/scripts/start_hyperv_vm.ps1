param(
  [string]$VmName = "Project-Infi-ARIS-Trixie-CoGOS",
  [string]$IsoPath = "E:\project-infi\AI OS Trixie Build\output\project-infi-aris-trixie-full-os-v10.iso",
  [int64]$MemoryStartupBytes = 6GB,
  [int]$ProcessorCount = 4,
  [int64]$DiskSizeBytes = 20GB,
  [string]$VmRoot = "$env:PUBLIC\Documents\Hyper-V\Project-Infi"
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
    throw "Run this script from an elevated PowerShell window so Hyper-V can create and start the VM."
  }
}

Assert-Administrator

if (-not (Test-Path -LiteralPath $IsoPath)) {
  throw "ISO not found: $IsoPath"
}

Import-Module Hyper-V

$vmPath = Join-Path $VmRoot $VmName
$vhdPath = Join-Path $vmPath "$VmName.vhdx"
New-Item -ItemType Directory -Force -Path $vmPath | Out-Null

$existing = Get-VM -Name $VmName -ErrorAction SilentlyContinue
if (-not $existing) {
  New-VM -Name $VmName -Generation 1 -MemoryStartupBytes $MemoryStartupBytes -Path $VmRoot -NoVHD | Out-Null
  New-VHD -Path $vhdPath -SizeBytes $DiskSizeBytes -Dynamic | Out-Null
  Add-VMHardDiskDrive -VMName $VmName -Path $vhdPath | Out-Null
  Add-VMDvdDrive -VMName $VmName -Path $IsoPath | Out-Null
} else {
  if (-not (Get-VMDvdDrive -VMName $VmName -ErrorAction SilentlyContinue)) {
    Add-VMDvdDrive -VMName $VmName -Path $IsoPath | Out-Null
  } else {
    Set-VMDvdDrive -VMName $VmName -Path $IsoPath | Out-Null
  }
}

Set-VMProcessor -VMName $VmName -Count $ProcessorCount | Out-Null
Set-VMMemory -VMName $VmName -DynamicMemoryEnabled $false -StartupBytes $MemoryStartupBytes | Out-Null
Set-VMFirmware -VMName $VmName -EnableSecureBoot Off -ErrorAction SilentlyContinue | Out-Null

$dvd = Get-VMDvdDrive -VMName $VmName
$disk = Get-VMHardDiskDrive -VMName $VmName | Select-Object -First 1
Set-VMBios -VMName $VmName -StartupOrder $dvd, $disk | Out-Null

if ((Get-VM -Name $VmName).State -ne "Running") {
  Start-VM -Name $VmName | Out-Null
}

Start-Process vmconnect.exe -ArgumentList "localhost", $VmName

Write-Host "Started Hyper-V VM: $VmName"
Write-Host "Attached ISO: $IsoPath"
