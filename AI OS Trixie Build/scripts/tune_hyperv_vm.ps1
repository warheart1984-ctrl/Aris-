param(
  [string]$VmName = "Project-Infi-ARIS-Trixie-CoGOS",
  [int64]$MemoryStartupBytes = 6GB,
  [int]$ProcessorCount = 4,
  [string]$StatusPath = "E:\project-infi\AI OS Trixie Build\output\hyperv-v10-tune-status.txt"
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
    throw "Run this script from an elevated PowerShell window so Hyper-V settings can be changed."
  }
}

Assert-Administrator
Import-Module Hyper-V

$vm = Get-VM -Name $VmName
$wasRunning = $vm.State -eq "Running"

if ($wasRunning) {
  Stop-VM -Name $VmName -TurnOff -Force
}

Set-VMProcessor -VMName $VmName -Count $ProcessorCount | Out-Null
Set-VMMemory -VMName $VmName -DynamicMemoryEnabled $false -StartupBytes $MemoryStartupBytes | Out-Null

if ($wasRunning) {
  Start-VM -Name $VmName | Out-Null
}

Get-VM -Name $VmName |
  Select-Object Name, State, Generation, MemoryStartup, DynamicMemoryEnabled, ProcessorCount |
  Format-List |
  Out-File -Encoding utf8 $StatusPath

Write-Host "Tuned Hyper-V VM: $VmName"
Write-Host "Processors: $ProcessorCount"
Write-Host "Fixed startup memory: $MemoryStartupBytes"
