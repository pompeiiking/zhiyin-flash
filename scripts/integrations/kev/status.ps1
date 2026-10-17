$ErrorActionPreference = 'Stop'
$stateFile = Join-Path $PSScriptRoot 'service.json'
if (-not (Test-Path -LiteralPath $stateFile)) { Write-Host 'Kev is stopped.'; return }
$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
$process = Get-Process -Id $state.processId -ErrorAction SilentlyContinue
if (-not $process -or $process.StartTime.ToUniversalTime().Ticks -ne ([datetime]$state.startedUtc).ToUniversalTime().Ticks) {
    Write-Host 'Kev is stopped. Recent error log:'
    Get-Content -LiteralPath (Join-Path $PSScriptRoot 'logs\server.err.log') -Tail 20 -ErrorAction SilentlyContinue
    return
}
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$($state.port)/v1/models" -TimeoutSec 5 | ConvertTo-Json -Depth 8
} catch {
    Write-Host "Process $($state.processId) is running; API not ready yet. Recent error log:"
    Get-Content -LiteralPath (Join-Path $PSScriptRoot 'logs\server.err.log') -Tail 12 -ErrorAction SilentlyContinue
}
