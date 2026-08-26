param([string]$Root)
$ErrorActionPreference = 'SilentlyContinue'
$ports = @(8000, 5173)
foreach ($port in $ports) {
  $connections = Get-NetTCPConnection -LocalPort $port -State Listen
  foreach ($conn in $connections) {
    $procId = $conn.OwningProcess
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId"
    $cmd = [string]$proc.CommandLine
    $isFundScope = ($cmd -match 'FundScope') -or ($cmd.Contains($Root))
    if ($isFundScope) {
      Stop-Process -Id $procId -Force
      Start-Sleep -Milliseconds 350
    } else {
      exit 2
    }
  }
}
exit 0
