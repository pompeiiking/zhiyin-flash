param([int]$Port = 8009)
$ErrorActionPreference = 'Stop'
$KevRoot = $PSScriptRoot
$stateFile = Join-Path $KevRoot 'service.json'
$pythonExe = Join-Path $KevRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $stateFile) {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $running = Get-Process -Id $state.processId -ErrorAction SilentlyContinue
    if ($running -and $running.StartTime.ToUniversalTime().Ticks -eq ([datetime]$state.startedUtc).ToUniversalTime().Ticks) {
        Write-Host "Kev is already running (PID $($state.processId)), http://127.0.0.1:$($state.port)"
        return
    }
}
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'The dedicated Python environment is missing.' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use."
}
$oldEnvironment = @{}
Get-ChildItem Env: | ForEach-Object { $oldEnvironment[$_.Name] = $_.Value }
try {
    . (Join-Path $KevRoot 'env.ps1')
    $env:HF_HUB_OFFLINE = '1'
    $env:TRANSFORMERS_OFFLINE = '1'
    $process = Start-Process -FilePath $pythonExe -ArgumentList @('-m', 'kev.serve', '--run', 'jaredpalmer/kev-0.8b@v1.0', '--host', '127.0.0.1', '--port', "$Port") -WorkingDirectory (Join-Path $KevRoot 'src') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $KevRoot 'logs\server.out.log') -RedirectStandardError (Join-Path $KevRoot 'logs\server.err.log') -PassThru
    @{ processId = $process.Id; startedUtc = $process.StartTime.ToUniversalTime().ToString('o'); port = $Port; model = 'jaredpalmer/kev-0.8b@v1.0' } | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding utf8
    Write-Host "Kev started (PID $($process.Id)), http://127.0.0.1:$Port"
    Write-Host 'The model needs time to load. Run status.ps1 to check readiness.'
} finally {
    Get-ChildItem Env: | Where-Object { -not $oldEnvironment.ContainsKey($_.Name) } | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
    foreach ($name in $oldEnvironment.Keys) { Set-Item -LiteralPath "Env:$name" -Value $oldEnvironment[$name] }
}
