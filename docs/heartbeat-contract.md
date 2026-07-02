# Strategy heartbeat contract (S1–S6)

Each strategy worker writes a JSON heartbeat file for process liveness and activity observability.

## File location

```
Core Strategy/run-state/S1.heartbeat.json
Core Strategy/run-state/S2.heartbeat.json
...
Core Strategy/run-state/S6.heartbeat.json
```

On a typical Windows install:

`D:\Web3Tools\Core Strategy\run-state\S{n}.heartbeat.json`

Writes are atomic (temp file + replace). Write failures must not crash the strategy process.

## Required fields

| Field | Type | Description |
|-------|------|-------------|
| `strategy` | string | `S1` … `S6` |
| `worker` | string | Canonical worker id (e.g. `onchain_narrative_radar`) |
| `pid` | number | Strategy process PID |
| `parentPid` | number \| null | Parent process PID when available |
| `status` | string | See status values below |
| `phase` | string | Current phase label (e.g. `scan`, `sleep`, `idle`) |
| `lastHeartbeatAt` | string | ISO-8601 UTC timestamp of last write |
| `lastLoopStartedAt` | string \| null | ISO-8601 UTC when current loop started |
| `lastLoopFinishedAt` | string \| null | ISO-8601 UTC when last loop finished |
| `lastSuccessAt` | string \| null | ISO-8601 UTC of last successful loop |
| `lastErrorAt` | string \| null | ISO-8601 UTC of last error |
| `lastError` | string \| null | Truncated error message |
| `loopCount` | number | Completed loop counter |
| `errorCount` | number | Cumulative error counter |
| `nextRunAt` | string \| null | ISO-8601 UTC when sleep ends / next run expected |
| `expectedIntervalSec` | number | Nominal loop interval |
| `scriptName` | string | Entry script filename |

## Status values

| Status | Meaning |
|--------|---------|
| `starting` | Process bootstrapping |
| `running` | Active work (scan, idle between sub-steps, etc.) |
| `sleeping` | Waiting until `nextRunAt` |
| `error` | Last loop ended in error state |

Phases are free-form strings (`scan`, `sleep`, `idle`, `error`, worker-specific names).

## Watchdog semantics (Phase 2A)

The dry-run watchdog in `launchers/strategy_watchdog.py` evaluates each strategy:

| Condition | Typical decision |
|-----------|------------------|
| `sleeping` + `nextRunAt` in the future | **ok** (`sleeping_ok`) |
| `lastHeartbeatAt` age ≤ stale threshold | **ok** (`healthy` or `idle`) |
| Stale heartbeat (age > stale, ≤ offline) | **would_warn** or **would_restart** (per strategy config) |
| Offline heartbeat (age > offline) | **would_warn** or **would_restart** |
| PID file / heartbeat PID not running | **would_restart** (`process_stopped`) |
| Missing heartbeat file | **would_warn** or **would_restart** |
| Invalid JSON | **would_warn** |
| `status == error` | **would_warn** (escalates to **would_restart** on repeated errors) |

Long-running scan phases (S1, S4) should call `maybe_beat()` during work so heartbeat age stays fresh.

## Monitoring stack integration

- **Web3-MonitoringBacked** reads heartbeat files and exposes **process status** (PID alive) and **activity status** (heartbeat freshness, sleep schedule) separately via `/api/core-strategy/workers`.
- **Web3-MonitoringTools** displays process dot (running/stopped) and activity text (healthy / idle / stale / offline) in the strategy workbench.

Heartbeat files are the preferred activity source when present (`sourceOfTruth: strategy_heartbeat`).

## Implementation

Vendored helper: `strategy_heartbeat.py` in each strategy repo (identical copies).

Local dev copy (unversioned): `Core Strategy/strategy_heartbeat.py` when using the monorepo-style folder layout.
