param([Parameter(Mandatory=$true)][string]$ProjectRoot)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') {
    Write-Output '{"status":"skipped","reason":"not_windows"}'
    exit 0
}
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$target = Join-Path $root 'start.bat'
if (-not (Test-Path -LiteralPath $target)) { throw 'Missing project start.bat.' }
$desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
if (-not $desktop) { throw 'Cannot locate the current user desktop.' }
$linkPath = Join-Path $desktop 'Print Extractor AI.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $root
$shortcut.Description = 'Start Print Extractor AI and open the local workbench'
$shortcut.WindowStyle = 1
$shortcut.Save()
@{status='created';path=$linkPath;target=$target} | ConvertTo-Json -Compress
