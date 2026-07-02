# Phase 2A thin launcher for strategy_watchdog.py (dry-run only).
param(
    [switch]$Once,
    [int]$Interval = 60,
    [string]$Strategy,
    [switch]$Json,
    [switch]$Verbose
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

$argsList = @("--dry-run", "true")
if ($Once) { $argsList += "--once" }
if ($Interval -gt 0) { $argsList += @("--interval", "$Interval") }
if ($Strategy) { $argsList += @("--strategy", $Strategy) }
if ($Json) { $argsList += "--json" }
if ($Verbose) { $argsList += "--verbose" }

& $python $watchdogPy @argsList
exit $LASTEXITCODE
