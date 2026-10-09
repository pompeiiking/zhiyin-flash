[CmdletBinding()]
param(
    [string]$Config = '',
    [string]$Python = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 does not populate PSScriptRoot while binding defaults.
if ([string]::IsNullOrWhiteSpace($Config)) {
    $Config = Join-Path (Split-Path $PSScriptRoot -Parent) '.platform/executor.json'
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'This launcher requires Windows. Use the documented manual worker commands on other hosts.'
}

# Parse native Windows arguments instead of accepting an arbitrary substring in
# CommandLine (for example, a different script mentioning our path in its text).
if (-not ('Zhiyin.ModuleWorkers.NativeArguments' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace Zhiyin.ModuleWorkers {
    public static class NativeArguments {
        [DllImport("shell32.dll", SetLastError = true)]
        static extern IntPtr CommandLineToArgvW([MarshalAs(UnmanagedType.LPWStr)] string commandLine, out int count);
        [DllImport("kernel32.dll")]
        static extern IntPtr LocalFree(IntPtr memory);
        public static string[] Split(string commandLine) {
            int count;
            IntPtr memory = CommandLineToArgvW(commandLine, out count);
            if (memory == IntPtr.Zero) throw new InvalidOperationException("Cannot parse process command line.");
            try {
                string[] result = new string[count];
                for (int index = 0; index < count; index++)
                    result[index] = Marshal.PtrToStringUni(Marshal.ReadIntPtr(memory, index * IntPtr.Size));
                return result;
            } finally { LocalFree(memory); }
        }
    }
}
'@
}

function Resolve-RequiredFile([string]$Path, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label file does not exist: $Path"
    }
    $resolved = (Resolve-Path -LiteralPath $Path).ProviderPath
    if ($resolved -match '["\r\n]') { throw "$Label path contains unsupported command-line characters." }
    return $resolved
}

function Get-WorkerProcess([int]$WorkerProcessId) {
    return Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $WorkerProcessId" -ErrorAction Stop
}

function Test-WorkerProcess($Process, [string]$WorkerPath, [string]$ConfigPath, [string]$PythonPath) {
    if ($null -eq $Process -or [string]::IsNullOrWhiteSpace([string]$Process.CommandLine) -or
        [string]::IsNullOrWhiteSpace([string]$Process.ExecutablePath)) { return $false }
    if (-not [string]::Equals([IO.Path]::GetFullPath($Process.ExecutablePath), $PythonPath, [StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }
    $arguments = [Zhiyin.ModuleWorkers.NativeArguments]::Split($Process.CommandLine)
    $scriptIndex = 1
    if ($arguments.Length -gt 1 -and $arguments[1] -eq '-u') { $scriptIndex = 2 }
    if ($arguments.Length -ne ($scriptIndex + 3) -or $arguments[$scriptIndex + 1] -ne '--config') { return $false }
    if (-not [IO.Path]::IsPathRooted($arguments[$scriptIndex]) -or
        -not [IO.Path]::IsPathRooted($arguments[$scriptIndex + 2])) { return $false }
    return [string]::Equals([IO.Path]::GetFullPath($arguments[$scriptIndex]), $WorkerPath, [StringComparison]::OrdinalIgnoreCase) -and
        [string]::Equals([IO.Path]::GetFullPath($arguments[$scriptIndex + 2]), $ConfigPath, [StringComparison]::OrdinalIgnoreCase)
}

function Save-WorkerPid([string]$PidFile, [int]$WorkerProcessId) {
    $temporary = "$PidFile.tmp"
    [IO.File]::WriteAllText($temporary, "$WorkerProcessId`n", (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $PidFile -Force
}

function Start-OrReuseWorker([string]$Name, [string]$WorkerPath, [string]$ConfigPath,
                            [string]$PythonPath, [string]$WorkingDirectory, [string]$LogDirectory) {
    $pidFile = Join-Path $LogDirectory "$Name.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $stored = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        $workerProcessId = 0
        if (-not [int]::TryParse($stored, [ref]$workerProcessId) -or $workerProcessId -le 0) {
            throw "Invalid PID file: $pidFile. Inspect it before retrying; no process has been stopped."
        }
        $existing = Get-WorkerProcess $workerProcessId
        if ($null -ne $existing) {
            if (-not (Test-WorkerProcess $existing $WorkerPath $ConfigPath $PythonPath)) {
                throw "PID $workerProcessId in $pidFile belongs to a different or unverifiable command. No process has been stopped; inspect the PID file before retrying."
            }
            return [pscustomobject]@{ Worker = $Name; ProcessId = $workerProcessId; Status = 'reused'; Logs = $LogDirectory }
        }
    }

    # Recover a lost PID file for a worker launched with the same absolute paths.
    $matches = @(Get-CimInstance -ClassName Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction Stop |
        Where-Object { Test-WorkerProcess $_ $WorkerPath $ConfigPath $PythonPath })
    if ($matches.Count -gt 1) {
        throw "Multiple matching $Name processes exist. Inspect them manually; this launcher never stops processes."
    }
    if ($matches.Count -eq 1) {
        Save-WorkerPid $pidFile $matches[0].ProcessId
        return [pscustomobject]@{ Worker = $Name; ProcessId = $matches[0].ProcessId; Status = 'adopted'; Logs = $LogDirectory }
    }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $stdout = Join-Path $LogDirectory "$Name-$stamp.stdout.log"
    $stderr = Join-Path $LogDirectory "$Name-$stamp.stderr.log"
    $arguments = '-u "' + $WorkerPath + '" --config "' + $ConfigPath + '"'
    try {
        # Windows PowerShell 5.1 has no Start-Process -Environment parameter.
        # Apply UTF-8 to the inherited child environment and restore the caller.
        $previousUtf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'Process')
        try {
            [Environment]::SetEnvironmentVariable('PYTHONUTF8', '1', 'Process')
            $started = Start-Process -FilePath $PythonPath -ArgumentList $arguments -WorkingDirectory $WorkingDirectory `
                -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
        }
        finally { [Environment]::SetEnvironmentVariable('PYTHONUTF8', $previousUtf8, 'Process') }
        Save-WorkerPid $pidFile $started.Id
        Start-Sleep -Milliseconds 1500
        $started.Refresh()
        if ($started.HasExited) {
            throw "Worker exited with code $($started.ExitCode)."
        }
        if (-not (Test-WorkerProcess (Get-WorkerProcess $started.Id) $WorkerPath $ConfigPath $PythonPath)) {
            throw 'Started process command line could not be verified.'
        }
    }
    catch {
        throw "Could not start or verify $Name. No process was stopped. Inspect stdout: $stdout and stderr: $stderr. $($_.Exception.GetType().Name)"
    }
    return [pscustomobject]@{ Worker = $Name; ProcessId = $started.Id; Status = 'started'; Logs = "$stdout | $stderr" }
}

$repoRoot = (Resolve-Path -LiteralPath (Split-Path $PSScriptRoot -Parent)).ProviderPath
$configPath = Resolve-RequiredFile $Config 'Worker config'
try {
    $settings = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
}
catch { throw "Worker config is not readable JSON: $configPath" }
$required = @('repository', 'state_directory', 'compose_file', 'workbench_env_file', 'staging_env_file', 'source_base_commit', 'rollout_strategy')
foreach ($key in $required) {
    if ($settings.PSObject.Properties.Name -notcontains $key -or [string]::IsNullOrWhiteSpace([string]$settings.$key)) {
        throw "Worker config is missing required field: $key"
    }
}
if ($settings.rollout_strategy -ne 'blue_green' -or $settings.source_base_commit -notmatch '^[a-f0-9]{40}$') {
    throw 'Worker config requires rollout_strategy=blue_green and a full 40-character source_base_commit.'
}
foreach ($key in @('repository', 'state_directory', 'compose_file', 'workbench_env_file', 'staging_env_file')) {
    if (-not [IO.Path]::IsPathRooted([string]$settings.$key)) { throw "Config path must be absolute: $key" }
    if (-not (Test-Path -LiteralPath $settings.$key)) { throw "Config path does not exist: $key" }
}
$journalPath = Join-Path $settings.state_directory 'bluegreen/deployment.json'
if (-not (Test-Path -LiteralPath $journalPath -PathType Leaf)) {
    throw "Blue/green is not initialized. Complete prepare-migration and activate-migration first. Expected journal: $journalPath"
}
try { $journal = Get-Content -LiteralPath $journalPath -Raw -Encoding UTF8 | ConvertFrom-Json }
catch { throw "Blue/green journal is not readable JSON: $journalPath" }
if ($journal.PSObject.Properties.Name -notcontains 'active_slot' -or $journal.active_slot -notin @('blue', 'green') -or
    $journal.PSObject.Properties.Name -notcontains 'active_revision' -or $journal.active_revision -notmatch '^[a-f0-9]{40}$') {
    throw 'Blue/green journal has no valid active slot/revision. Complete initial migration before starting workers.'
}
$route = $null
try { $route = Invoke-RestMethod -Uri 'http://127.0.0.1:8015/__platform_route' -TimeoutSec 5 }
catch { Write-Warning '8015 route is temporarily unreachable. Starting from the initialized journal so pending recovery can proceed; inspect worker logs.' }
if ($null -ne $route) {
    if ($route.PSObject.Properties.Name -notcontains 'slot' -or $route.PSObject.Properties.Name -notcontains 'revision' -or
        $route.PSObject.Properties.Name -notcontains 'generation' -or $route.generation -lt 1) {
        throw '8015 does not return a valid initialized blue/green route.'
    }
    $known = $route.slot -eq $journal.active_slot -and $route.revision -eq $journal.active_revision
    if ($journal.PSObject.Properties.Name -contains 'pending' -and $null -ne $journal.pending -and
        $journal.pending.PSObject.Properties.Name -contains 'target_slot' -and $journal.pending.PSObject.Properties.Name -contains 'target_revision') {
        $known = $known -or ($route.slot -eq $journal.pending.target_slot -and $route.revision -eq $journal.pending.target_revision)
    }
    if (-not $known) { throw '8015 route is outside the active/pending journal. Refusing to launch workers against an unknown deployment.' }
}

$pythonCommand = Get-Command -Name $Python -CommandType Application -ErrorAction Stop | Select-Object -First 1
$pythonPath = Resolve-RequiredFile $pythonCommand.Source 'Python executable'
$workers = @('module_source_worker', 'module_executor')
$workerPaths = @{}
foreach ($name in $workers) { $workerPaths[$name] = Resolve-RequiredFile (Join-Path $PSScriptRoot "$name.py") $name }
$logDirectory = Join-Path ([IO.Path]::GetFullPath($settings.state_directory)) 'host-workers'
[IO.Directory]::CreateDirectory($logDirectory) | Out-Null
$launchLock = $null
try {
    $launchLock = [IO.File]::Open((Join-Path $logDirectory 'launcher.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    foreach ($name in $workers) {
        Start-OrReuseWorker $name $workerPaths[$name] $configPath $pythonPath $repoRoot $logDirectory |
            Format-Table -AutoSize
    }
    Write-Host 'Workers are running as hidden host processes. This does not install a service or a startup task.'
}
finally {
    if ($null -ne $launchLock) { $launchLock.Dispose() }
}
