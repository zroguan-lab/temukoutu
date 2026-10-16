param([string]$PythonExe = 'python')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
try {
    $bundled = Join-Path $root '.runtime\cpython-3.11.15-windows-x86_64-none\python.exe'
    if ($PythonExe -eq 'python' -and (Test-Path -LiteralPath $bundled)) { $PythonExe = $bundled }
    if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) { throw 'Python 3.11 or 3.12 required. Install Python and enable Add to PATH.' }
    & $PythonExe -c "import sys; assert sys.version_info[:2] in [(3,11),(3,12)], 'Python 3.11 or 3.12 required'"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or 3.12 required for the included dependency lock files.' }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 20.19+ required.' }
    & node -e "const [a,b]=process.versions.node.split('.').map(Number); if(a<20 || (a===20 && b<19))process.exit(1)"
    if ($LASTEXITCODE -ne 0) { throw 'Node.js 20.19+ required.' }
    New-Item -ItemType Directory -Force (Join-Path $root '.tmp') | Out-Null
    $env:TEMP = Join-Path $root '.tmp'
    $env:TMP = $env:TEMP
    & $PythonExe -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    $pythonExe = Join-Path $root '.venv\Scripts\python.exe'
    $minorVersion = & $pythonExe -c "import sys; print(sys.version_info.minor)"
    $requirements = if ($minorVersion -eq '11') { 'backend\requirements-lock311.txt' } else { 'backend\requirements-lock.txt' }
    if (-not (Test-Path -LiteralPath $requirements)) { $requirements = 'backend\requirements.txt' }
    & $pythonExe -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed; check network/proxy.' }
    & npm.cmd ci --prefix frontend --cache .tmp/npm-cache
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed; check network/proxy.' }
    & npm.cmd run build --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    & $pythonExe -c "from extractor_core import extract; import cv2, fastapi, PIL; print('CPU engine imports OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }
    & $pythonExe (Join-Path $root 'scripts\post_install.py')
    if ($LASTEXITCODE -ne 0) { throw 'Dependencies installed, but desktop shortcut creation failed. Run scripts/post_install.py again.' }
    Write-Host 'Installed successfully. P0 requires no model files; nothing was downloaded as a model.' -ForegroundColor Green
    Write-Host 'Double-click start.bat to open http://127.0.0.1:7860'
} catch { Write-Error $_; exit 1 }
