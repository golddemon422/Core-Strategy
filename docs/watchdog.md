# Strategy watchdog (Phase 2A / 2B)

Health checker for S1–S6. **Default is dry-run (Phase 2A).** Phase 2B adds optional execute mode (`--execute`) that may restart **at most one** strategy per run with safety guards.

## Phase

| Phase | Mode | Behavior |
|-------|------|----------|
| **2A** | Default (dry-run) | Reports `would_warn` / `would_restart`; never restarts |
| **2B** | `--execute` | May perform one real restart per run via `launch_strategy.ps1 -Force` |

## Inputs

| Input | Default path |
|-------|----------------|
| Heartbeat files | `Core Strategy/run-state/S{n}.heartbeat.json` |
| PID files | `launchers/pids/S{n}.pid` |
| Restart launcher | `launchers/launch_strategy.ps1 -Strategy S{n} -Force` |
| Restart history | `Core Strategy/run-state/watchdog-restart-history.json` |

## Usage

Dry-run (default):

```bash
python launchers/strategy_watchdog.py --once
python launchers/strategy_watchdog.py --once --strategy S3
python launchers/strategy_watchdog.py --interval 60
python launchers/strategy_watchdog.py --once --verbose
python launchers/strategy_watchdog.py --once --json
```

Execute mode (Phase 2B — real restart when warranted):

```bash
python launchers/strategy_watchdog.py --once --execute
python launchers/strategy_watchdog.py --once --execute --strategy S2
python launchers/strategy_watchdog.py --once --execute --restart-cooldown-sec 900 --max-restarts-per-hour 2
```

PowerShell wrapper:

```powershell
powershell -File launchers/strategy_watchdog.ps1 -Once
powershell -File launchers/strategy_watchdog.ps1 -Once -Strategy S3
powershell -File launchers/strategy_watchdog.ps1 -Once -Execute
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
| Restart history | `Core Strategy/run-state/watchdog-restart-history.json` |

## CLI options

| Flag | Description |
|------|-------------|
| `--once` | Single check then exit |
| `--interval N` | Loop every N seconds (default 60) |
| `--dry-run true` | Dry-run (default). Ignored when `--execute` is set |
| `--execute` | Phase 2B: allow one real restart when warranted |
| `--restart-cooldown-sec N` | Min seconds between restarts per strategy (default 900) |
| `--max-restarts-per-hour N` | Max restart attempts per strategy per hour (default 2) |
| `--post-restart-verify-timeout-sec N` | Heartbeat verification timeout (default 120) |
| `--post-restart-verify-interval-sec N` | Verification poll interval (default 5) |
| `--restart-history-path PATH` | Override restart history JSON path |
| `--strategy S3` | Check one strategy (required for S4 execute unless explicitly selected) |
| `--verbose` | Console + file logging |
| `--json` | Print results JSON to stdout |
| `--state-dir`, `--pid-dir`, `--report-path`, `--log-path` | Override paths |

## Phase 2B execute rules

- **Default remains dry-run.** Only `--execute` performs real restarts.
- **One strategy per run.** If multiple `would_restart`, picks one deterministically (S4 deprioritized unless `--strategy S4`).
- **Business-SLA warn-only:** S5/S6 `business_api_fail`, `business_sla_stale`, `business_scan_stale` never trigger restart.
- **S3 sleeping_ok** with future `nextRunAt` never restarts.
- **PID safety:** verifies PID command line matches strategy script marker before restart; skips with `restart_skipped_unsafe_pid_match` if not verifiable.
- **Cooldown / rate limit:** default 900s cooldown, max 2 restarts/hour per strategy.
- **Post-restart verification:** polls heartbeat until fresh `lastHeartbeatAt`, matching strategy/worker, and live PID (default 120s timeout).
- **Restart history:** atomic JSON write, max 200 events, corrupt file backed up and reset.

### Report action values

| Action | Meaning |
|--------|---------|
| `none` | Healthy / no action |
| `warn_only` | `would_warn` — no restart |
| `restart_skipped_dry_run` | Would restart but dry-run |
| `restart_skipped_cooldown` | Cooldown active |
| `restart_skipped_rate_limit` | Hourly limit reached |
| `restart_skipped_multiple_candidates` | Another strategy was chosen |
| `restart_skipped_unsafe_pid_match` | PID ownership not verified |
| `restart_attempted` | Launch invoked |
| `restart_success` | Verified after restart |
| `restart_failed` | Launcher or verification error |
| `restart_verification_timeout` | Heartbeat not verified in time |

## Tests

```bash
python launchers/test_strategy_watchdog.py
python -m py_compile launchers/strategy_watchdog.py launchers/test_strategy_watchdog.py
```

Tests use temporary fixtures only; they do not modify live heartbeat files or restart real strategies.

## Futures Radar business-SLA checks

Applies to **S5** (`heat_radar`) and **S6** (`accumulation_radar`).

Process heartbeat freshness is **not** enough for the Futures Radar / 合约雷达 channel. A worker can remain `sleeping_ok` while Binance API failures prevent report generation and Telegram sends.

Watchdog also inspects heartbeat business fields:

- `lastScanOutcome`
- `lastScanCompletedAt`
- `lastTelegramSentAt`
- `consecutiveScanFailures`
- `lastApiErrorAt`

### Business status rules

| Status | Condition | Decision |
|--------|-----------|----------|
| `business_api_fail` | `consecutiveScanFailures >= 2` and `lastScanOutcome=binance_api_fail` | `would_warn` |
| `business_sla_stale` | `lastTelegramSentAt` older than 2× expected interval (default 3600s) | `would_warn` |
| `business_scan_stale` | `lastScanCompletedAt` older than 2× expected interval | `would_warn` |

These rules produce **`would_warn` only** — never auto-restart in Phase 2B.

## Current behavior summary

- Reads heartbeat JSON and PID files
- Checks process liveness (psutil → tasklist → `os.kill(pid, 0)`)
- Applies per-strategy stale/offline thresholds and sleep-schedule rules
- **Dry-run by default** — no restart unless `--execute`
- **Execute mode:** one restart max, with cooldown, rate limits, PID verification, post-restart heartbeat check
- Restart commands and actions logged in report `actions` array
