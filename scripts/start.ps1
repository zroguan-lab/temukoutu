param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
$address = 'http://127.0.0.1:7860'
$startupMutex = [System.Threading.Mutex]::new($false, 'Local\PrintExtractorAI-7860')
$ownsStartupMutex = $false
function Test-App {
    try {
        $health = Invoke-RestMethod -Uri "$address/api/health" -TimeoutSec 2
        return $health.app -eq 'print-extractor-ai'
    } catch { return $false }
}
try {
    try { $ownsStartupMutex = $startupMutex.WaitOne(30000) }
    catch [System.Threading.AbandonedMutexException] { $ownsStartupMutex = $true }
    if (-not $ownsStartupMutex) { throw 'Application startup is already in progress. Wait and retry.' }
    # The backend reads the user-owned AI settings; no Key is placed on this command line.
    if (Test-App) {
        Write-Host 'Print Extractor AI is already running.'
        if (-not $NoBrowser) { Start-Process $address }
        exit 0
    }
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,7860)
    try { $probe.Start() } catch { throw 'Port 7860 is occupied by another application. Stop it and retry.' } finally { $probe.Stop() }
    $pythonExe = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run install.bat first: missing Python environment.' }
    if (-not (Test-Path -LiteralPath (Join-Path $root 'frontend\dist\index.html'))) { throw 'Run install.bat first: missing frontend build.' }
    $logs = Join-Path $root 'artifacts'
    New-Item -ItemType Directory -Force $logs | Out-Null
    $outLog = Join-Path $logs 'server.out.log'
    $errLog = Join-Path $logs 'server.err.log'
    $process = Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','7860','--workers','1') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    $ok = $false
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        if ($process.HasExited) { break }
        if (Test-App) { $ok = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ok) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
        if (Test-Path -LiteralPath $errLog) { Get-Content -LiteralPath $errLog -Tail 30 }
        throw 'Startup failed. See artifacts/server.err.log.'
    }
    $process.Id | Set-Content -LiteralPath (Join-Path $logs 'server.pid')
    Write-Host "Print Extractor AI ready: $address (PID $($process.Id))" -ForegroundColor Green
    if (-not $NoBrowser) { Start-Process $address }
} catch { Write-Error $_; exit 1 }
finally {
    if ($ownsStartupMutex) { $startupMutex.ReleaseMutex() }
    $startupMutex.Dispose()
}
