param([string]$KevRoot = 'E:\ai-models\kev')
$ErrorActionPreference = 'Stop'
$resolvedRoot = (Resolve-Path -LiteralPath $KevRoot).Path
$startScript = Join-Path $resolvedRoot 'start.ps1'
if (-not (Test-Path -LiteralPath $startScript -PathType Leaf)) { throw 'Kev start.ps1 is missing.' }
$startupFolder = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupFolder 'Zhiyin Kev.lnk'
$shellObject = New-Object -ComObject WScript.Shell
$shortcut = $shellObject.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $startScript + '"'
$shortcut.WorkingDirectory = $resolvedRoot
$shortcut.WindowStyle = 7
$shortcut.Description = 'Start the local Kev intent router after this user signs in.'
$shortcut.Save()
Write-Output "Installed current-user startup: $shortcutPath"
