# MonitoringTools (Web3-MonitoringTools, port 3000) process discovery and PID file hygiene.
# Dot-source from launch_monitoring_tools.ps1, status_monitoring_tools.ps1.

. (Join-Path $PSScriptRoot "_service_pid.ps1")

$script:MonitoringToolsPort = 3000
$script:MonitoringToolsServiceName = "MonitoringTools"

function Get-MonitoringToolsRepoPath {
    param([string]$RepoRoot = "D:\Web3Tools")
    return Join-Path $RepoRoot "Web3-MonitoringTools"
}

function Get-MonitoringToolsRunStateDir {
    param([string]$RepoRoot = "D:\Web3Tools")
    return Join-Path $RepoRoot "Core Strategy\run-state"
}

function Get-MonitoringToolsRunLogsDir {
    param([string]$RepoRoot = "D:\Web3Tools")
    return Join-Path $RepoRoot "Core Strategy\run-logs"
}

function Get-MonitoringToolsWorkerPidFile {
    param([string]$RepoRoot = "D:\Web3Tools")
    return Join-Path (Get-MonitoringToolsRunStateDir -RepoRoot $RepoRoot) "MonitoringTools.worker.pid"
}

function Get-MonitoringToolsLauncherPidFile {
    param([string]$RepoRoot = "D:\Web3Tools")
    return Join-Path (Get-MonitoringToolsRunStateDir -RepoRoot $RepoRoot) "MonitoringTools.launcher.pid"
}

function Test-MonitoringToolsNodeProcess {
    param($Proc)
    if (-not $Proc) { return $false }
    if ($Proc.Name -notmatch '^node(\.exe)?$') { return $false }
    $cmd = [string]$Proc.CommandLine
    if (-not $cmd) { return $false }
    if ($cmd -notlike '*next*') { return $false }
    if ($cmd -like '*Web3-MonitoringTools*' -or $cmd -like '*web3-monitor*') { return $true }
    if ($cmd -like '*MonitoringTools*') { return $true }
    return $false
}

function Test-MonitoringToolsWorkerProcess {
    param($Proc)
    if (-not $Proc) { return $false }
    if ($Proc.Name -notmatch '^(powershell|pwsh)(\.exe)?$') { return $false }
    $cmd = [string]$Proc.CommandLine
    if (-not $cmd) { return $false }
    return ($cmd -like '*_monitoring_tools_worker.ps1*')
}

function Get-MonitoringToolsRelatedProcesses {
    param([string]$RepoRoot = "D:\Web3Tools")
    $toolsPath = Get-MonitoringToolsRepoPath -RepoRoot $RepoRoot
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            if (-not $_.CommandLine) { return $false }
            $cmd = $_.CommandLine
            if ($cmd -like "*$toolsPath*" -and ($cmd -like '*next*' -or $cmd -like '*npm*')) { return $true }
            if ($cmd -like '*launch_monitoring_tools.ps1*') { return $true }
            if ($cmd -like '*_monitoring_tools_worker.ps1*') { return $true }
            if ($cmd -like '*start_MonitoringTools.cmd*') { return $true }
            return $false
        }
}

function Get-MonitoringToolsListenerPid {
    param([int]$Port = $script:MonitoringToolsPort)
    $listenerPid = Get-ServicePortListenerPid -Port $Port
    if (-not $listenerPid) { return $null }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$listenerPid" -ErrorAction SilentlyContinue
    if (Test-MonitoringToolsNodeProcess -Proc $proc) { return $listenerPid }
    return $null
}

function Get-MonitoringToolsSupervisorPid {
    param([string]$RepoRoot = "D:\Web3Tools")
    $launcherPid = Read-ServicePidFile -PidFile (Get-MonitoringToolsLauncherPidFile -RepoRoot $RepoRoot)
    if ($launcherPid) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$launcherPid" -ErrorAction SilentlyContinue
        if ($proc -and (Test-MonitoringToolsWorkerProcess -Proc $proc)) {
            return $launcherPid
        }
    }
    $related = @(Get-MonitoringToolsRelatedProcesses -RepoRoot $RepoRoot)
    $worker = @($related | Where-Object { Test-MonitoringToolsWorkerProcess -Proc $_ } | Select-Object -First 1)
    if ($worker) { return [int]$worker.ProcessId }
    return $null
}

function Apply-MonitoringToolsLaunchEnv {
    if (-not $env:NODE_OPTIONS) {
        $env:NODE_OPTIONS = "--max-old-space-size=4096"
    } elseif ($env:NODE_OPTIONS -notlike '*max-old-space-size*') {
        $env:NODE_OPTIONS = "$($env:NODE_OPTIONS) --max-old-space-size=4096"
    }
    if (-not $env:NEXT_PUBLIC_ONCHAIN_POLL_MS) {
        $env:NEXT_PUBLIC_ONCHAIN_POLL_MS = "15000"
    }
    if (-not $env:NEXT_PUBLIC_ONCHAIN_WORKER_POLL_MS) {
        $env:NEXT_PUBLIC_ONCHAIN_WORKER_POLL_MS = "8000"
    }
}

function Get-MonitoringToolsStatus {
    param([string]$RepoRoot = "D:\Web3Tools")

    $launcherPidFile = Get-MonitoringToolsLauncherPidFile -RepoRoot $RepoRoot
    $workerPidFile = Get-MonitoringToolsWorkerPidFile -RepoRoot $RepoRoot
    $launcherPid = Read-ServicePidFile -PidFile $launcherPidFile
    $workerPid = Read-ServicePidFile -PidFile $workerPidFile
    $listenerPid = Get-MonitoringToolsListenerPid
    $supervisorPid = Get-MonitoringToolsSupervisorPid -RepoRoot $RepoRoot
    $related = @(Get-MonitoringToolsRelatedProcesses -RepoRoot $RepoRoot)
    $nodePids = @($related | Where-Object { Test-MonitoringToolsNodeProcess -Proc $_ } | ForEach-Object { $_.ProcessId })

    $launcherAlive = $false
    $launcherIsWorker = $false
    if ($launcherPid) {
        $launcherProc = Get-CimInstance Win32_Process -Filter "ProcessId=$launcherPid" -ErrorAction SilentlyContinue
        if ($launcherProc) {
            $launcherAlive = $true
            $launcherIsWorker = Test-MonitoringToolsWorkerProcess -Proc $launcherProc
        }
    }

    $workerAlive = $false
    $workerIsNpm = $false
    if ($workerPid) {
        $workerProc = Get-CimInstance Win32_Process -Filter "ProcessId=$workerPid" -ErrorAction SilentlyContinue
        if ($workerProc) {
            $workerAlive = $true
            $workerIsNpm = (
                $workerProc.Name -match '^(cmd|node)(\.exe)?$' -or
                (Test-MonitoringToolsNodeProcess -Proc $workerProc)
            )
        }
    }

    $launcherStale = ($null -ne $launcherPid) -and (-not $launcherAlive -or -not $launcherIsWorker)
    $workerStale = ($null -ne $workerPid) -and (-not $workerAlive)

    $overall = "stopped"
    if ($listenerPid -and ($supervisorPid -or $launcherAlive)) {
        $overall = "running"
    } elseif ($launcherStale -or $workerStale) {
        $overall = "stale_pid"
    } elseif ($supervisorPid -and -not $listenerPid) {
        $overall = "port_down"
    } elseif ($listenerPid -and -not $supervisorPid) {
        $overall = "port_down"
    }

    [pscustomobject]@{
        service            = $script:MonitoringToolsServiceName
        status             = $overall
        port               = $script:MonitoringToolsPort
        launcher_pid_file  = $launcherPidFile
        worker_pid_file    = $workerPidFile
        launcher_pid       = $launcherPid
        worker_pid         = $workerPid
        supervisor_pid     = $supervisorPid
        launcher_alive     = $launcherAlive
        launcher_is_worker = $launcherIsWorker
        worker_alive       = $workerAlive
        worker_is_npm      = $workerIsNpm
        launcher_stale     = $launcherStale
        worker_stale       = $workerStale
        listener_pid       = $listenerPid
        related_pids       = @($related | ForEach-Object { $_.ProcessId })
        node_pids          = $nodePids
        running_on_port    = ($null -ne $listenerPid)
        out_log            = Join-Path (Get-MonitoringToolsRunLogsDir -RepoRoot $RepoRoot) "MonitoringTools.out.log"
        err_log            = Join-Path (Get-MonitoringToolsRunLogsDir -RepoRoot $RepoRoot) "MonitoringTools.err.log"
    }
}

function Clear-StaleMonitoringToolsPidFiles {
    param(
        [string]$RepoRoot = "D:\Web3Tools",
        [switch]$Refresh
    )
    $status = Get-MonitoringToolsStatus -RepoRoot $RepoRoot
    $actions = @()

    if ($status.launcher_stale) {
        Remove-ServicePidFile -PidFile $status.launcher_pid_file
        $actions += "removed_stale_launcher_pid"
        if ($Refresh -and $status.supervisor_pid) {
            Write-ServicePidFile -PidFile $status.launcher_pid_file -ProcessId $status.supervisor_pid
            $actions += "refreshed_launcher_from_supervisor"
        }
    }

    if ($status.worker_stale) {
        Remove-ServicePidFile -PidFile $status.worker_pid_file
        $actions += "removed_stale_worker_pid"
        if ($Refresh -and $status.listener_pid) {
            Write-ServicePidFile -PidFile $status.worker_pid_file -ProcessId $status.listener_pid
            $actions += "refreshed_worker_from_listener"
        }
    }

    if ($actions.Count -eq 0) { return $null }
    return ($actions -join ",")
}

function Rotate-MonitoringToolsLogsIfLarge {
    param(
        [string]$RunLogs,
        [int64]$MaxBytes = 104857600
    )
    $archiveDir = Join-Path $RunLogs "archive"
    New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"

    foreach ($name in @("MonitoringTools.out.log", "MonitoringTools.err.log")) {
        $path = Join-Path $RunLogs $name
        if (-not (Test-Path $path)) { continue }
        $len = (Get-Item -LiteralPath $path).Length
        if ($len -lt $MaxBytes) { continue }
        $base = $name -replace '\.log$', ''
        $dest = Join-Path $archiveDir ("{0}.{1}.log" -f $base, $stamp)
        Move-Item -LiteralPath $path -Destination $dest -Force
        New-Item -ItemType File -Force -Path $path | Out-Null
        Write-Host "[monitoring_tools] rotated $name ($([math]::Round($len / 1MB, 1)) MB) -> $dest"
    }
}

function Stop-MonitoringToolsProcesses {
    param([string]$RepoRoot = "D:\Web3Tools")

    $listenerPid = Get-MonitoringToolsListenerPid
    if ($listenerPid) {
        Write-Host "Stopping listener PID $listenerPid on :$($script:MonitoringToolsPort) (graceful)"
        Stop-Process -Id $listenerPid -ErrorAction SilentlyContinue
        for ($i = 0; $i -lt 12; $i++) {
            if (-not (Get-MonitoringToolsListenerPid)) { break }
            Start-Sleep -Seconds 1
        }
        $stillListening = Get-MonitoringToolsListenerPid
        if ($stillListening) {
            Write-Host "Force stopping listener PID $stillListening"
            Stop-Process -Id $stillListening -Force -ErrorAction SilentlyContinue
        }
    }

    $related = @(Get-MonitoringToolsRelatedProcesses -RepoRoot $RepoRoot)
    foreach ($proc in $related) {
        if ($proc.ProcessId -eq $PID) { continue }
        Write-Host "Stopping PID $($proc.ProcessId) ($($proc.Name))"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }

    Start-Sleep -Seconds 1
    Remove-ServicePidFile -PidFile (Get-MonitoringToolsLauncherPidFile -RepoRoot $RepoRoot)
    Remove-ServicePidFile -PidFile (Get-MonitoringToolsWorkerPidFile -RepoRoot $RepoRoot)
    return $related.Count
}

function Get-LogTailLines {
    param(
        [string]$Path,
        [int]$Lines = 8
    )
    if (-not (Test-Path $Path)) { return @("(missing)") }
    try {
        return @(Get-Content -LiteralPath $Path -Tail $Lines -ErrorAction Stop)
    } catch {
        return @("(read error: $($_.Exception.Message))")
    }
}
