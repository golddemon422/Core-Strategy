# Strategy and monitoring repository map

Canonical GitHub remotes and default branches for the Web3Tools stack.

## Strategy workers (S1–S6)

| ID | Local folder | GitHub repo | Branch | Worker ID |
|----|--------------|-------------|--------|-----------|
| S1 | `Core Strategy/onChain-radar` | [golddemon422/onChain-radar](https://github.com/golddemon422/onChain-radar) | `onchain-radar-v2` | `onchain_narrative_radar` |
| S2 | `Core Strategy/binance-alpha-monitor` | [golddemon422/binance-alpha-monitor](https://github.com/golddemon422/binance-alpha-monitor) | `main` | `binance_alpha_monitor` |
| S3 | `Core Strategy/OI_Funding_rate_scaner` | [golddemon422/OI_Funding_rate_scaner](https://github.com/golddemon422/OI_Funding_rate_scaner) | `main` | `oi_funding_scanner` |
| S4 | `Core Strategy/Ai-Trading` | [golddemon422/Ai-Trading](https://github.com/golddemon422/Ai-Trading) | `main` | `futures_alpha_scanner` |
| S5 | `Core Strategy/accumulation-fastsignal-radar` | [golddemon422/accumulation-fastsignal-radar](https://github.com/golddemon422/accumulation-fastsignal-radar) | `main` | `heat_radar` |
| S6 | `Core Strategy/accumulation-radar` | [golddemon422/accumulation-radar](https://github.com/golddemon422/accumulation-radar) | `radar-v1` | `accumulation_radar` |

Each strategy repo vendors `strategy_heartbeat.py` at its root for deploy-safe imports.

## Monitoring stack

| Component | Local folder | GitHub repo | Branch |
|-----------|--------------|-------------|--------|
| API / worker observability | `Web3-MonitoringBacked` | [golddemon422/Web3-MonitoringBacked](https://github.com/golddemon422/Web3-MonitoringBacked) | `main` |
| Web UI | `Web3-MonitoringTools` | [golddemon422/Web3-MonitoringTools](https://github.com/golddemon422/Web3-MonitoringTools) | `master` |

## Orchestration (this repo)

| Component | Clone path | GitHub repo | Branch |
|-----------|------------|-------------|--------|
| Launchers, watchdog, docs | `Core-Strategy-Orchestration` | [golddemon422/Core-Strategy](https://github.com/golddemon422/Core-Strategy) | `master` |

## Runtime paths (local Windows layout)

| Purpose | Path |
|---------|------|
| Heartbeat files | `D:\Web3Tools\Core Strategy\run-state\S{n}.heartbeat.json` |
| Strategy PID files | `D:\Web3Tools\launchers\pids\S{n}.pid` |
| Strategy logs | `D:\Web3Tools\Core Strategy\run-logs\` |
| Launch scripts | `D:\Web3Tools\launchers\` (operational) or `launchers/` in this repo (versioned) |

`D:\Web3Tools\Core Strategy` is **not** a git repository. It is a runtime directory containing nested clones of S1–S6 plus shared `run-state` and `run-logs`.
