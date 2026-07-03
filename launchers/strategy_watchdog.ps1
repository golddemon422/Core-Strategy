# Strategy watchdog launcher (Phase 2A dry-run default; Phase 2B with -Execute).
param(
    [switch]$Once,
    [int]$Interval = 60,
    [string]$Strategy,
    [switch]$Json,
    [switch]$Verbose,
    [switch]$Execute,
    [int]$RestartCooldownSec = 900,
    [int]$MaxRestartsPerHour = 2,
    [int]$PostRestartVerifyTimeoutSec = 120,
    [int]$PostRestartVerifyIntervalSec = 5,
    [string]$RestartHistoryPath
)

$ErrorActionPreference = "Stop"

$repoRoot = "D:\Web3Tools"
$coreRoot = Join-Path $repoRoot "Core Strategy"
$watchdogPy = Join-Path $repoRoot "launchers\strategy_watchdog.py"
$venvPython = Join-Path $coreRoot "onChain-radar\.venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    $python = "python"
}

$argsList = @()
if (-not $Execute) {
    $argsList += @("--dry-run", "true")
} else {
    $argsList += "--execute"
}
if ($Once) { $argsList += "--once" }
if ($Interval -gt 0) { $argsList += @("--interval", "$Interval") }
if ($Strategy) { $argsList += @("--strategy", $Strategy) }
if ($Json) { $argsList += "--json" }
if ($Verbose) { $argsList += "--verbose" }
$argsList += @("--restart-cooldown-sec", "$RestartCooldownSec")
$argsList += @("--max-restarts-per-hour", "$MaxRestartsPerHour")
$argsList += @("--post-restart-verify-timeout-sec", "$PostRestartVerifyTimeoutSec")
$argsList += @("--post-restart-verify-interval-sec", "$PostRestartVerifyIntervalSec")
if ($RestartHistoryPath) {
    $argsList += @("--restart-history-path", $RestartHistoryPath)
}

& $python $watchdogPy @argsList
exit $LASTEXITCODE
