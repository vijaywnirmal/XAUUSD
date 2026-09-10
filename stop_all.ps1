# Stop everything started by run_all.ps1 (backend, frontend, live bot, monitor).
$pat = 'webapp\.backend\.main|-m livebot|-m monitor|next dev|next-server|npm run dev'
$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match $pat -and $_.Name -match 'python|node|cmd'
}
if (-not $procs) { Write-Host "nothing running"; return }
foreach ($p in $procs) {
    Write-Host ("stopping pid {0}  {1}" -f $p.ProcessId, $p.Name)
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
