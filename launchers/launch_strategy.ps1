param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("S1", "S2", "S3", "S4", "S5", "S6", "HEARTBEAT")]
    [string]$Strategy,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = "D:\Web3Tools"
$coreRoot = Join-Path $repoRoot "Core Strategy"
$venvPython = Join-Path $coreRoot "onChain-radar\.venv\Scripts\python.exe"
$runLogs = Join-Path $coreRoot "run-logs"
$pidDir = Join-Path $repoRoot "launchers\pids"

New-Item -ItemType Directory -Force -Path $runLogs | Out-Null
New-Item -ItemType Directory -Force -Path $pidDir | Out-Null

$configs = @{
    S1 = @{
        Name = "S1"
        WorkingDirectory = Join-Path $coreRoot "onChain-radar"
        Script = "s1_on_chain_narrative_radar.py"
        OutLog = Join-Path $runLogs "S1.out.log"
        ErrLog = Join-Path $runLogs "S1.err.log"
        Env = @{
            ONCHAIN_RADAR_LOG = (Join-Path $runLogs "s1_runtime.log")
            ONCHAIN_RADAR_DB = (Join-Path $coreRoot "onChain-radar\onchain_radar_v2.db")
            # Phase 2B dual-write + Phase 3 MonitoringBacked PG-first reads (see launch_monitoring_backed.ps1).
            ONCHAIN_RADAR_PG_MIRROR = "1"
            ONCHAIN_RADAR_PG_MIRROR_QUEUE_MAX = "5000"
            ONCHAIN_RADAR_PG_MIRROR_FLUSH_SIZE = "200"
            ONCHAIN_RADAR_PG_MIRROR_FLUSH_SECONDS = "2"
            ONCHAIN_RADAR_PG_MIRROR_CONNECT_TIMEOUT = "3"
            ONCHAIN_RADAR_PG_MIRROR_PRUNE_SNAPSHOTS = "0"
            # Smart-money buys: GET events from MonitoringBacked (walletLabel enriched from wallet_watch_targets)
            WALLET_WATCH_EVENTS_URL = "http://127.0.0.1:3001/api/wallet-watch/events"
            # ROBIN: scan + board + TG full (immediate + summary); set summary_only to demote immediate
            S1_ROBIN_SCAN_ENABLED = "1"
            S1_ROBIN_BOARD_ENABLED = "1"
            S1_ROBIN_TG_ENABLED = "1"
            S1_ROBIN_TG_MODE = "full"
            S1_ROBIN_TREND_SUMMARY_ENABLED = "1"
            S1_ROBIN_SCAN_DRY_RUN = "0"
            ROBIN_RPC_URL = "https://rpc.mainnet.chain.robinhood.com"
            S1_ROBIN_LOOKBACK_BLOCKS = "3000"
            ONCHAIN_BOARD_REFRESH_LOOKBACK_DAYS = "30"
            # TEMP relaxed 2026-08-25 afternoon: small caps (was 0 / hung TG).
            # Keep board refresh tiny so hydrate cannot block the scan cycle.
            ONCHAIN_BOARD_REFRESH_CAP = "24"
            ONCHAIN_BOARD_REFRESH_STALE_SLOTS = "32"
            ONCHAIN_BOARD_REFRESH_CHAIN_MIN = "robin=8,base=4,bsc=4"
            # BSC flap/7777 suffix reactivation — limited seat budget
            BSC_SUFFIX_REACTIVATION_ENABLED = "1"
            BSC_SUFFIX_REACTIVATION_FALLBACK_SEARCH_QUERIES = "four.meme,4444,ffff,7777,flap,BSC meme,BNB,pump bsc"
            BSC_SUFFIX_WATCHLIST_SEED_LOOKBACK_SEC = "172800"
            BSC_SUFFIX_METRICS_SEED_LIMIT = "120"
            BSC_SUFFIX_REACTIVATION_GMGN_LIMIT = "120"
            # Parallel per-chain discovery (BASE/BSC/ETH/ROBIN/SOL); opt-out with RADAR_PARALLEL_SCAN_NEW_PAIRS=0
            RADAR_PARALLEL_SCAN_NEW_PAIRS = "1"
            RADAR_SQLITE_BUSY_TIMEOUT_MS = "60000"
            S1_METRICS_FLUSH_EVERY = "1"
            # Watchlist enrich budget per scan (all-chain cold-token digestion)
            WATCHLIST_LOAD_CAP = "1000"
            WATCHLIST_FETCH_POOL = "5000"
            WATCHLIST_PER_CHAIN_MIN = "60"
            # Never-enriched / stale-metric watchlist must keep seats (all chains)
            WATCHLIST_NEVER_ENRICHED_RESERVE = "350"
            WATCHLIST_NEVER_ENRICHED_FETCH_PER_CHAIN = "450"
            WATCHLIST_STALE_ENRICH_MAX_AGE_SEC = "1800"
            # Auto-prune dormant never-enriched bloat (keep young window 15d — align FLR-class empty-scan)
            WATCHLIST_NEVER_ENRICHED_MAX_AGE_SEC = "1296000"
            WATCHLIST_NEVER_ENRICHED_PRUNE_LAST_SEEN_GRACE_SEC = "43200"
            WATCHLIST_NEVER_ENRICHED_PRUNE_LIMIT = "2500"
            SCAN_ENRICH_CAP = "650"
            SCAN_ENRICH_PER_CHAIN_MIN = "50"
            SCAN_ENRICH_SUFFIX_RESERVE = "40"
            SCAN_ENRICH_STALE_RESERVE = "220"
            SCAN_ENRICH_STALE_RESERVE_FRAC = "0.40"
            # Opportunity observation: refresh frozen unified-feed quotes (all chains)
            OPPORTUNITY_QUOTE_STALE_SEC = "900"
            OPPORTUNITY_LIVE_QUOTE_REFRESH_PER_LOOP = "120"
            OUTER_15M_BURST_M15_PCT = "12"
            OUTER_15M_BURST_M5_PCT = "8"
            WALLET_WATCH_GAP_DISCOVERY_ENABLED = "1"
            WALLET_WATCH_GAP_DISCOVERY_LIMIT = "180"
            # Inner-pool bonding track (T1-T4): P0 launchpad harvest + 1m/3m micro metrics
            # Small harvest budget — full 40 blocked TG for 100-200s.
            ENABLE_LAUNCHPAD_PRIMARY_SCAN = "1"
            LAUNCHPAD_PRIMARY_SCAN_LIMIT = "12"
            ENABLE_1M_3M_METRICS = "1"
            # Mid-round fresh discover: wallet buys + multi-chain Dex/boosts during long enrich
            S1_FRESH_DISCOVER_PULSE_ENABLED = "1"
            S1_FRESH_DISCOVER_PULSE_SEC = "90"
            S1_FRESH_DISCOVER_DEX_ENABLED = "1"
            S1_FRESH_DISCOVER_BOOSTS_ENABLED = "1"
            S1_FRESH_DISCOVER_MAX_PER_CHAIN = "16"
            S1_FRESH_DISCOVER_MIN_VOL_H1 = "400"
            S1_FRESH_DISCOVER_MIN_LIQ = "800"
            S1_FRESH_DISCOVER_BSC_ENABLED = "1"
            S1_FRESH_DISCOVER_COLD_REQUEUE_MAX = "48"
            # Align cold/young empty rescan with 15d young TTL (was 2h — dropped FLR-class tokens)
            S1_FRESH_DISCOVER_COLD_REQUEUE_LOOKBACK_SEC = "1296000"
            S1_YOUNG_EMPTY_RESCAN_ENABLED = "1"
            S1_YOUNG_EMPTY_RESCAN_MAX_AGE_SEC = "1296000"
            # Dormant full-pool scan abandoned — keep OFF (new/young/active paths only)
            SOL_PUMP_REACTIVATION_ENABLED = "0"
            SOL_DORMANT_AUTO_SEED_LIMIT = "0"
            S1_FRESH_DISCOVER_SOL_DORMANT_ENABLED = "0"
            BSC_PAIRCREATED_SAFETY_LOOKBACK_BLOCKS = "24000"
            # Admit non-suffix / developer contracts from PairCreated + PCS V3 (not launchpad-only).
            BSC_LAUNCHPAD_ONLY = "0"
            # Old-pool / developer-contract breakouts (ETH+BASE+BSC)
            EVM_OLD_BREAKOUT_ENABLED = "1"
            EVM_OLD_BREAKOUT_MAX_PER_CHAIN = "40"
            EVM_OLD_BREAKOUT_MIN_AGE_HOURS = "48"
            EVM_OLD_BREAKOUT_MIN_MC = "150000"
            EVM_OLD_BREAKOUT_MIN_LIQ = "25000"
            EVM_OLD_BREAKOUT_MIN_H1 = "6"
            EVM_OLD_BREAKOUT_MIN_H6 = "12"
            EVM_OLD_BREAKOUT_MIN_H24 = "15"
        }
    }
    S2 = @{
        Name = "S2"
        WorkingDirectory = Join-Path $coreRoot "binance-alpha-monitor"
        Script = "s2_alpha_monitor.py"
        OutLog = Join-Path $runLogs "S2.out.log"
        ErrLog = Join-Path $runLogs "S2.err.log"
        Env = @{}
    }
    S3 = @{
        Name = "S3"
        WorkingDirectory = Join-Path $coreRoot "OI_Funding_rate_scaner"
        Script = "s3_oi_funding_rate_scanner.py"
        OutLog = Join-Path $runLogs "S3.out.log"
        ErrLog = Join-Path $runLogs "S3.err.log"
        Env = @{}
    }
    S4 = @{
        Name = "S4"
        WorkingDirectory = Join-Path $coreRoot "Ai-Trading"
        Script = "s4_futures_alpha_autonomous_trading_v1.py"
        OutLog = Join-Path $runLogs "S4.out.log"
        ErrLog = Join-Path $runLogs "S4.err.log"
        Env = @{}
    }
    S5 = @{
        Name = "S5"
        WorkingDirectory = Join-Path $coreRoot "accumulation-fastsignal-radar"
        Script = "s5_accumulation_radar.py"
        OutLog = Join-Path $runLogs "S5.out.log"
        ErrLog = Join-Path $runLogs "S5.err.log"
        Env = @{}
    }
    S6 = @{
        Name = "S6"
        WorkingDirectory = Join-Path $coreRoot "accumulation-radar"
        Script = "s6_accumulation_radar.py"
        OutLog = Join-Path $runLogs "S6.out.log"
        ErrLog = Join-Path $runLogs "S6.err.log"
        Env = @{}
    }
    HEARTBEAT = @{
        Name = "HEARTBEAT"
        WorkingDirectory = $coreRoot
        Script = "worker_heartbeat_daemon.py"
        OutLog = Join-Path $runLogs "WorkerHeartbeat.out.log"
        ErrLog = Join-Path $runLogs "WorkerHeartbeat.err.log"
        Env = @{}
    }
}

$config = $configs[$Strategy]
$pidFile = Join-Path $pidDir ($Strategy + ".pid")

# S1: load shared secrets/DB from MonitoringBacked .env when unset in launcher Env.
if ($Strategy -eq "S1") {
    $backendEnv = Join-Path $repoRoot "Web3-MonitoringBacked\.env"
    $s1EnvKeys = @("DATABASE_URL", "STRATEGY_INGEST_SECRET", "WEB3_MONITOR_API_URL", "CORE_STRATEGY_INGEST_URL")
    if (Test-Path $backendEnv) {
        foreach ($line in Get-Content $backendEnv -Encoding UTF8) {
            $trimmed = $line.Trim()
            if ($trimmed -match '^\s*#') { continue }
            foreach ($envKey in $s1EnvKeys) {
                if ($config.Env.ContainsKey($envKey)) { continue }
                if ($trimmed -match ('^\s*' + [regex]::Escape($envKey) + '\s*=\s*"?([^"#]+)"?\s*$')) {
                    $config.Env[$envKey] = $Matches[1].Trim()
                }
            }
        }
    }
    if (-not $config.Env.ContainsKey("WEB3_MONITOR_API_URL") -and -not $config.Env.ContainsKey("CORE_STRATEGY_INGEST_URL")) {
        $config.Env["WEB3_MONITOR_API_URL"] = "http://127.0.0.1:3001"
    }
}

$strategyTreeScript = Join-Path $coreRoot "onChain-radar\tools\_strategy_process_tree.ps1"
if (-not (Test-Path $strategyTreeScript)) {
    throw "Missing strategy process helper: $strategyTreeScript"
}
. $strategyTreeScript

$treeSummary = Get-StrategyProcessTreeSummary -Strategy $Strategy
Write-Host "[strategy_launcher] strategy=$Strategy single_instance_check roots=$($treeSummary.independent_root_count) launchers=$($treeSummary.launcher_count) children=$($treeSummary.child_helper_count)"

if ($treeSummary.independent_root_count -gt 0) {
    if (-not $Force) {
        Write-Host "[strategy_launcher] strategy=$Strategy already_running root_pids=$($treeSummary.root_pids -join ', ')"
        Write-Host "Strategy $Strategy is already running (root Python PID(s): $($treeSummary.root_pids -join ', ')). Use -Force to restart."
        exit 1
    }
    Write-Host "[strategy_launcher] strategy=$Strategy force_restart stopping existing processes..."
    Stop-AllStrategyProcesses -Strategy $Strategy -PidFile $pidFile | Out-Null
} else {
    Clear-StaleStrategyPidFile -Strategy $Strategy -PidFile $pidFile
}

$envAssignments = @()
foreach ($pair in $config.Env.GetEnumerator()) {
    $value = [string]$pair.Value
    $escapedValue = $value.Replace("'", "''")
    $envAssignments += ('$env:{0} = ''{1}''' -f $pair.Key, $escapedValue)
}

$workingDirectory = [string]$config.WorkingDirectory
$scriptName = [string]$config.Script
$outLog = [string]$config.OutLog
$errLog = [string]$config.ErrLog

$workerLines = @(
    # Continue: strategy scripts log INFO to stderr; Stop would kill the worker on Windows.
    '$ErrorActionPreference = ''Continue'''
    ('Set-Location -LiteralPath ''{0}''' -f $workingDirectory.Replace("'", "''"))
)

# S1: do not inherit smoke-test / shell S1_DEBUG_TOKEN_* into the worker (opt-in diagnostics only).
if ($Strategy -eq "S1") {
    $workerLines += 'Remove-Item Env:S1_DEBUG_TOKEN_CHAIN -ErrorAction SilentlyContinue'
    $workerLines += 'Remove-Item Env:S1_DEBUG_TOKEN_ADDRESS -ErrorAction SilentlyContinue'
}

if ($envAssignments.Count -gt 0) {
    $workerLines += $envAssignments
}

# S6: Win/Python 3.14 spawns a child interpreter; shell 1>>/2>> attaches to the idle parent.
# S6 tees run-logs in-script instead (see s6_accumulation_radar.py).
if ($Strategy -eq "S6") {
    $workerLines += ('& ''{0}'' -u ''{1}''' -f $venvPython.Replace("'", "''"), $scriptName.Replace("'", "''"))
} else {
    $workerLines += ('& ''{0}'' ''{1}'' 1>> ''{2}'' 2>> ''{3}''' -f $venvPython.Replace("'", "''"), $scriptName.Replace("'", "''"), $outLog.Replace("'", "''"), $errLog.Replace("'", "''"))
}

$workerCommand = $workerLines -join "; "

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = (Join-Path $PSHOME "powershell.exe")
$psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -Command ""& { $workerCommand }"""
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.WorkingDirectory = $workingDirectory

$proc = [System.Diagnostics.Process]::Start($psi)
if (-not $proc) {
    throw "Failed to start $Strategy"
}

Set-Content -Path $pidFile -Value $proc.Id -Encoding ascii

Write-Host "[strategy_launcher] strategy=$Strategy started launcher_pid=$($proc.Id)"
Write-Host "$Strategy started. PID=$($proc.Id)"
Write-Host "stdout: $outLog"
Write-Host "stderr: $errLog"
