param(
  [string]$VmName = "Project-Infi-ARIS-Trixie-CoGOS",
  [string]$StatusPath = "E:\project-infi\AI OS Trixie Build\output\hyperv-start.txt",
  [int64]$MemoryStartupBytes = 6GB,
  [int]$ProcessorCount = 4
)

$ErrorActionPreference = "Stop"

try {
  Import-Module Hyper-V

  $vm = Get-VM -Name $VmName
  if ($vm.State -ne "Running") {
    Set-VMProcessor -VMName $VmName -Count $ProcessorCount | Out-Null
    Set-VMMemory -VMName $VmName -DynamicMemoryEnabled $false -StartupBytes $MemoryStartupBytes | Out-Null
    Start-VM -Name $VmName
  }

  Get-VM -Name $VmName |
    Select-Object Name, State, Generation, MemoryStartup, ProcessorCount |
    Format-List |
    Out-File -Encoding utf8 $StatusPath

  Start-Process vmconnect.exe -ArgumentList "localhost", $VmName
} catch {
  ("ERROR: " + $_.Exception.Message) | Out-File -Encoding utf8 $StatusPath
  throw
}
