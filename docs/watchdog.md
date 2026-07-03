# Strategy watchdog (Phase 2A)

Dry-run health checker for S1–S6. Reports what **would** be done; does **not** restart or kill processes.

## Phase

**Phase 2A — dry-run only.** Real auto-restart is not implemented. Restart commands appear in the JSON report as references only.

## Inputs

| Input | Default path |
|-------|----------------|
| Heartbeat files | `Core Strategy/run-state/S{n}.heartbeat.json` |
| PID files | `launchers/pids/S{n}.pid` |
| Restart reference | `launchers/launch_strategy.ps1 -Strategy S{n} -Force` |

## Usage

From this repo root (or with paths adjusted for your install):

```bash
python launchers/strategy_watchdog.py --once
python launchers/strategy_watchdog.py --once --strategy S3
python launchers/strategy_watchdog.py --interval 60
python launchers/strategy_watchdog.py --once --verbose
python launchers/strategy_watchdog.py --once --json
```

PowerShell wrapper (uses `D:\Web3Tools` layout and onChain-radar venv Python when present):

```powershell
powershell -File launchers/strategy_watchdog.ps1 -Once
powershell -File launchers/strategy_watchdog.ps1 -Once -Strategy S3
powershell -File launchers/strategy_watchdog.ps1 -Interval 60 -Verbose
```

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | All strategies **ok** or **sleeping_ok** / **idle** |
| `1` | At least one **would_warn** |
| `2` | At least one **would_restart** (highest severity) |

Dry-run never executes restarts regardless of exit code.

## Outputs

| Output | Path |
|--------|------|
| Human-readable table | stdout |
| JSON report | `Core Strategy/run-state/watchdog-report.json` |
| Log file | `Core Strategy/run-logs/strategy_watchdog.log` |

## CLI options

| Flag | Description |
|------|-------------|
| `--once` | Single check then exit |
| `--interval N` | Loop every N seconds (default 60) |
| `--dry-run true` | Required; only `true` is supported in Phase 2A |
| `--strategy S3` | Check one strategy |
| `--verbose` | Console + file logging |
| `--json` | Print results JSON to stdout |
| `--state-dir`, `--pid-dir`, `--report-path`, `--log-path` | Override paths |

## Tests

```bash
python launchers/test_strategy_watchdog.py
python -m py_compile launchers/strategy_watchdog.py launchers/test_strategy_watchdog.py
```

Tests use temporary fixtures only; they do not modify live heartbeat files.

## Futures Radar business-SLA checks

Applies to **S5** (`heat_radar`) and **S6** (`accumulation_radar`).

Process heartbeat freshness is **not** enough for the Futures Radar / 合约雷达 channel. A worker can remain `sleeping_ok` while Binance API failures prevent report generation and Telegram sends.

Watchdog also inspects heartbeat business fields:

- `lastScanOutcome`
- `lastScanCompletedAt`
- `lastTelegramSentAt`
- `consecutiveScanFailures`
- `lastApiErrorAt`

### Business status rules (Phase 2A)

| Status | Condition | Decision |
|--------|-----------|----------|
| `business_api_fail` | `consecutiveScanFailures >= 2` and `lastScanOutcome=binance_api_fail` | `would_warn` |
| `business_sla_stale` | `lastTelegramSentAt` older than 2× expected interval (default 3600s) | `would_warn` |
| `business_scan_stale` | `lastScanCompletedAt` older than 2× expected interval | `would_warn` |

These rules produce **`would_warn` only** in Phase 2A. No auto-restart is triggered by business-SLA checks yet.

## Current behavior summary

- Reads heartbeat JSON and PID files
- Checks process liveness (psutil → tasklist → `os.kill(pid, 0)`)
- Applies per-strategy stale/offline thresholds and sleep-schedule rules
- **No restart or kill** in Phase 2A
- Restart commands logged in report `actions` array for Phase 2B planning
