param(
    [string]$ToolsRoot = "D:\Web3Tools\Web3-MonitoringTools",
    [string]$RunLogs = "D:\Web3Tools\Core Strategy\run-logs",
    [string]$RunState = "D:\Web3Tools\Core Strategy\run-state",
    [int64]$MaxLogBytes = 104857600
)

$ErrorActionPreference = "Continue"

$helper = Join-Path $PSScriptRoot "_monitoring_tools_process.ps1"
if (Test-Path $helper) {
    . $helper
} else {
    function Rotate-MonitoringToolsLogsIfLarge {
        param([string]$RunLogs, [int64]$MaxBytes = 104857600)
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
        }
    }
    function Apply-MonitoringToolsLaunchEnv {
        if (-not $env:NODE_OPTIONS) { $env:NODE_OPTIONS = "--max-old-space-size=4096" }
        if (-not $env:NEXT_PUBLIC_ONCHAIN_POLL_MS) { $env:NEXT_PUBLIC_ONCHAIN_POLL_MS = "15000" }
        if (-not $env:NEXT_PUBLIC_ONCHAIN_WORKER_POLL_MS) { $env:NEXT_PUBLIC_ONCHAIN_WORKER_POLL_MS = "8000" }
    }
    function Write-ServicePidFile {
        param([string]$PidFile, [int]$ProcessId)
        $dir = Split-Path -Parent $PidFile
        if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        Set-Content -Path $PidFile -Value $ProcessId -Encoding ascii
    }
}

$outLog = Join-Path $RunLogs "MonitoringTools.out.log"
$errLog = Join-Path $RunLogs "MonitoringTools.err.log"
New-Item -ItemType Directory -Force -Path $RunState | Out-Null
$launcherPidFile = Join-Path $RunState "MonitoringTools.launcher.pid"
$workerPidFile = Join-Path $RunState "MonitoringTools.worker.pid"

Set-Location -LiteralPath $ToolsRoot
Apply-MonitoringToolsLaunchEnv
Write-ServicePidFile -PidFile $launcherPidFile -ProcessId $PID

while ($true) {
    Rotate-MonitoringToolsLogsIfLarge -RunLogs $RunLogs -MaxBytes $MaxLogBytes
    $npmProc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm run dev 1>> `"$outLog`" 2>> `"$errLog`"" `
        -WorkingDirectory $ToolsRoot -PassThru -NoNewWindow
    if ($npmProc) {
        Write-ServicePidFile -PidFile $workerPidFile -ProcessId $npmProc.Id
        $npmProc.WaitForExit()
        $exitCode = $npmProc.ExitCode
    } else {
        $exitCode = -1
    }
    $ts = Get-Date -Format o
    "[$ts] monitoring_tools worker: npm dev exited exit_code=$exitCode" | Out-File -LiteralPath $errLog -Append -Encoding utf8
    Start-Sleep -Seconds 5
}
