param(
  [string]$VmName = "Project-Infi-ARIS-Trixie-CoGOS",
  [string]$IsoPath = "E:\project-infi\AI OS Trixie Build\output\project-infi-aris-trixie-full-os-v10.iso",
  [string]$StatusPath = "E:\project-infi\AI OS Trixie Build\output\hyperv-full-os-status.txt",
  [int64]$MemoryStartupBytes = 6GB,
  [int]$ProcessorCount = 4
)

$ErrorActionPreference = "Stop"

try {
  Import-Module Hyper-V

  if (-not (Test-Path -LiteralPath $IsoPath)) {
    throw "ISO not found: $IsoPath"
  }

  $vm = Get-VM -Name $VmName
  if ($vm.State -ne "Off") {
    Stop-VM -Name $VmName -TurnOff -Force
  }

  if (-not (Get-VMDvdDrive -VMName $VmName -ErrorAction SilentlyContinue)) {
    Add-VMDvdDrive -VMName $VmName -Path $IsoPath | Out-Null
  } else {
    Set-VMDvdDrive -VMName $VmName -Path $IsoPath | Out-Null
  }

  Set-VMProcessor -VMName $VmName -Count $ProcessorCount | Out-Null
  Set-VMMemory -VMName $VmName -DynamicMemoryEnabled $false -StartupBytes $MemoryStartupBytes | Out-Null

  Start-VM -Name $VmName
  Start-Process vmconnect.exe -ArgumentList "localhost", $VmName

  Get-VM -Name $VmName |
    Select-Object Name, State, Generation, MemoryStartup, ProcessorCount |
    Format-List |
    Out-File -Encoding utf8 $StatusPath

  Get-VMDvdDrive -VMName $VmName |
    Select-Object Path |
    Format-List |
    Out-File -Encoding utf8 -Append $StatusPath
} catch {
  ("ERROR: " + $_.Exception.Message) | Out-File -Encoding utf8 $StatusPath
  throw
}
