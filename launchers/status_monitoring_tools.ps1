param(
    [switch]$Refresh
)

$ErrorActionPreference = "Stop"

$repoRoot = "D:\Web3Tools"
$helper = Join-Path $repoRoot "launchers\_monitoring_tools_process.ps1"

if (-not (Test-Path $helper)) {
    throw "Missing MonitoringTools process helper: $helper"
}

. $helper

$staleAction = Clear-StaleMonitoringToolsPidFiles -RepoRoot $repoRoot -Refresh:$Refresh
if ($staleAction) {
    Write-Host ("pid_file_action={0}" -f $staleAction)
}

$status = Get-MonitoringToolsStatus -RepoRoot $repoRoot

Write-Host ("service={0}" -f $status.service)
Write-Host ("status={0}" -f $status.status)
Write-Host ("port={0}" -f $status.port)
Write-Host ("supervisor_pid={0}" -f ($(if ($status.supervisor_pid) { $status.supervisor_pid } else { "(none)" })))
Write-Host ("launcher_pid_file={0}" -f $status.launcher_pid_file)
Write-Host ("launcher_pid={0}" -f ($(if ($status.launcher_pid) { $status.launcher_pid } else { "(missing)" })))
Write-Host ("launcher_alive={0}" -f $status.launcher_alive)
Write-Host ("launcher_stale={0}" -f $status.launcher_stale)
Write-Host ("worker_pid_file={0}" -f $status.worker_pid_file)
Write-Host ("worker_pid={0}" -f ($(if ($status.worker_pid) { $status.worker_pid } else { "(missing)" })))
Write-Host ("worker_alive={0}" -f $status.worker_alive)
Write-Host ("worker_stale={0}" -f $status.worker_stale)
Write-Host ("listener_pid={0}" -f ($(if ($status.listener_pid) { $status.listener_pid } else { "(none)" })))
Write-Host ("running_on_port={0}" -f $status.running_on_port)
Write-Host ("related_pids={0}" -f (($status.related_pids -join ",") -replace "^$", "(none)"))
Write-Host ("node_pids={0}" -f (($status.node_pids -join ",") -replace "^$", "(none)"))

$portOccupant = Get-ServicePortListenerPid -Port $status.port
if ($portOccupant -and (-not $status.listener_pid -or $portOccupant -ne $status.listener_pid)) {
    $occupantProc = Get-CimInstance Win32_Process -Filter "ProcessId=$portOccupant" -ErrorAction SilentlyContinue
    $occupantCmd = if ($occupantProc) { $occupantProc.CommandLine } else { "" }
    Write-Host ("port_listener_pid={0}" -f $portOccupant)
    if ($occupantCmd) {
        $short = if ($occupantCmd.Length -gt 160) { $occupantCmd.Substring(0, 160) + "..." } else { $occupantCmd }
        Write-Host ("port_listener_cmd={0}" -f $short)
    }
} else {
    Write-Host ("port_listener_pid={0}" -f ($(if ($status.listener_pid) { $status.listener_pid } else { "(none)" })))
}

$httpOk = $false
if ($status.running_on_port) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$($status.port)" -UseBasicParsing -TimeoutSec 5
        $httpOk = ($resp.StatusCode -eq 200)
        Write-Host ("http_status={0}" -f $resp.StatusCode)
    } catch {
        Write-Host ("http_status=error message={0}" -f $_.Exception.Message)
    }
} else {
    Write-Host "http_status=skipped (not listening)"
}

Write-Host ("http_ok={0}" -f $httpOk)

if (Test-Path $status.out_log) {
    Write-Host ("out_log={0}" -f $status.out_log)
    Write-Host ("out_log_mtime={0}" -f (Get-Item -LiteralPath $status.out_log).LastWriteTime.ToString("o"))
} else {
    Write-Host ("out_log={0} (missing)" -f $status.out_log)
}

if (Test-Path $status.err_log) {
    Write-Host ("err_log={0}" -f $status.err_log)
    Write-Host ("err_log_mtime={0}" -f (Get-Item -LiteralPath $status.err_log).LastWriteTime.ToString("o"))
    Write-Host "--- err tail ---"
    Get-LogTailLines -Path $status.err_log -Lines 8 | ForEach-Object { Write-Host $_ }
} else {
    Write-Host ("err_log={0} (missing)" -f $status.err_log)
}

if (($status.launcher_stale -or $status.worker_stale) -and -not $Refresh) {
    Write-Host "Hint: stale PID file detected. launch_monitoring_tools.ps1 will clean on next launch, or run status with -Refresh."
}

if ($status.status -eq "stale_pid") {
    exit 3
}
if ($status.status -eq "port_down") {
    exit 4
}
if ($status.status -ne "running") {
    exit 1
}
exit 0
