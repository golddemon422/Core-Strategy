param(
    [switch]$Force,
    [switch]$StatusOnly
)

$ErrorActionPreference = "Stop"

$repoRoot = "D:\Web3Tools"
$coreRoot = Join-Path $repoRoot "Core Strategy"
$toolsRoot = Join-Path $repoRoot "Web3-MonitoringTools"
$runLogs = Join-Path $coreRoot "run-logs"
$runState = Join-Path $coreRoot "run-state"
$helper = Join-Path $repoRoot "launchers\_monitoring_tools_process.ps1"
$workerScript = Join-Path $repoRoot "launchers\_monitoring_tools_worker.ps1"

if (-not (Test-Path $helper)) {
    throw "Missing MonitoringTools process helper: $helper"
}
if (-not (Test-Path $workerScript)) {
    throw "Missing MonitoringTools worker script: $workerScript"
}
if (-not (Test-Path $toolsRoot)) {
    throw "Missing Web3-MonitoringTools at: $toolsRoot"
}

. $helper

if ($StatusOnly) {
    & (Join-Path $repoRoot "launchers\status_monitoring_tools.ps1")
    exit $LASTEXITCODE
}

New-Item -ItemType Directory -Force -Path $runLogs | Out-Null
New-Item -ItemType Directory -Force -Path $runState | Out-Null

$staleAction = Clear-StaleMonitoringToolsPidFiles -RepoRoot $repoRoot
if ($staleAction) {
    Write-Host "[monitoring_tools] pid_cleanup=$staleAction"
}

$status = Get-MonitoringToolsStatus -RepoRoot $repoRoot
$portOccupant = Get-ServicePortListenerPid -Port $script:MonitoringToolsPort
if ($portOccupant -and -not $status.listener_pid) {
    $occupantProc = Get-CimInstance Win32_Process -Filter "ProcessId=$portOccupant" -ErrorAction SilentlyContinue
    $occupantName = if ($occupantProc) { $occupantProc.Name } else { "unknown" }
    Write-Host "[monitoring_tools] port_check :$($script:MonitoringToolsPort) occupied by PID=$portOccupant name=$occupantName (not MonitoringTools next dev)"
}

Write-Host "[monitoring_tools] port_check listener=$($status.listener_pid) launcher_pid=$($status.launcher_pid) worker_pid=$($status.worker_pid) stale_launcher=$($status.launcher_stale) stale_worker=$($status.worker_stale)"

if ($status.running_on_port -and $status.supervisor_pid) {
    if (-not $Force) {
        Write-Host "MonitoringTools is already running (supervisor PID $($status.supervisor_pid), listener PID $($status.listener_pid)). Use -Force to restart."
        exit 1
    }
    Write-Host "[monitoring_tools] force_restart stopping existing processes..."
    Stop-MonitoringToolsProcesses -RepoRoot $repoRoot | Out-Null
} elseif ($status.running_on_port -and -not $Force) {
    Write-Host "Port :$($script:MonitoringToolsPort) is in use but worker supervisor not detected. Use -Force to restart related processes."
    exit 1
} else {
    Clear-StaleMonitoringToolsPidFiles -RepoRoot $repoRoot | Out-Null
}

$outLog = Join-Path $runLogs "MonitoringTools.out.log"
$errLog = Join-Path $runLogs "MonitoringTools.err.log"
$launcherPidFile = Get-MonitoringToolsLauncherPidFile -RepoRoot $repoRoot
$workerPidFile = Get-MonitoringToolsWorkerPidFile -RepoRoot $repoRoot

Rotate-MonitoringToolsLogsIfLarge -RunLogs $runLogs
Apply-MonitoringToolsLaunchEnv

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = (Join-Path $PSHOME "powershell.exe")
$psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$workerScript`" -ToolsRoot `"$toolsRoot`" -RunLogs `"$runLogs`" -RunState `"$runState`""
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.WorkingDirectory = $toolsRoot

foreach ($key in @("NODE_OPTIONS", "NEXT_PUBLIC_ONCHAIN_POLL_MS", "NEXT_PUBLIC_ONCHAIN_WORKER_POLL_MS")) {
    $val = [Environment]::GetEnvironmentVariable($key, "Process")
    if ($val) {
        $psi.EnvironmentVariables[$key] = $val
    }
}

$proc = [System.Diagnostics.Process]::Start($psi)
if (-not $proc) {
    throw "Failed to start MonitoringTools worker"
}

Write-ServicePidFile -PidFile $launcherPidFile -ProcessId $proc.Id
Write-Host "[monitoring_tools] started supervisor_pid=$($proc.Id) waiting for :$($script:MonitoringToolsPort)..."

$listenerPid = $null
$httpOk = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    $listenerPid = Get-MonitoringToolsListenerPid
    if ($listenerPid) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$($script:MonitoringToolsPort)" -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -eq 200) {
                $httpOk = $true
                break
            }
        } catch {
            # next dev may still be compiling
        }
    }
}

if (-not $listenerPid) {
    Write-Host "MonitoringTools supervisor started but port :$($script:MonitoringToolsPort) is not listening yet. Check logs:"
    Write-Host "stdout: $outLog"
    Write-Host "stderr: $errLog"
    Write-Host "--- err tail ---"
    Get-LogTailLines -Path $errLog -Lines 12 | ForEach-Object { Write-Host $_ }
    exit 2
}

if ($listenerPid) {
    Write-ServicePidFile -PidFile $workerPidFile -ProcessId $listenerPid
}

Write-Host "MonitoringTools listening. supervisor_pid=$($proc.Id) listener_pid=$listenerPid http_ok=$httpOk"
Write-Host "launcher_pid_file: $launcherPidFile"
Write-Host "worker_pid_file: $workerPidFile (listener node)"
Write-Host "stdout: $outLog"
Write-Host "stderr: $errLog"

if (-not $httpOk) {
    Write-Host "Warning: port is listening but HTTP check did not return 200 within timeout."
    exit 2
}

exit 0
