# Launch backend, frontend, live bot (paper) and monitor as background processes.
# Logs go to .\run_logs\ ; stop everything with .\stop_all.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$logs = Join-Path $root "run_logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Start-Bg([string]$name, [string]$exe, [string[]]$exeArgs, [string]$wd) {
    $p = Start-Process -FilePath $exe -ArgumentList $exeArgs -WorkingDirectory $wd `
        -RedirectStandardOutput (Join-Path $logs "$name.out.log") `
        -RedirectStandardError  (Join-Path $logs "$name.err.log") `
        -PassThru -WindowStyle Hidden
    "{0,-9} pid {1}" -f $name, $p.Id | Write-Host
}

Write-Host "starting from $root ..."
Start-Bg "backend"  "python"  @("-m","uvicorn","webapp.backend.main:app","--host","127.0.0.1","--port","8000") $root
Start-Sleep 2
Start-Bg "frontend" "cmd.exe" @("/c","npm","run","dev") (Join-Path $root "webapp\frontend")
Start-Bg "livebot"  "python"  @("-m","livebot") $root
Start-Bg "monitor"  "python"  @("-m","monitor","--source","mt5") $root

Write-Host ""
Write-Host "logs:  $logs"
Write-Host "UI:    http://localhost:3000"
Write-Host "check: curl localhost:8000/livebot/status   /  curl localhost:8000/monitor/snapshot"
Write-Host "stop:  .\stop_all.ps1"
