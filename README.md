# Core-Strategy (orchestration)

This repository is **orchestration only**. It does not contain the full source code for strategy workers S1–S6.

## What lives here

- **Launchers and watchdog** — scripts to observe and (eventually) manage strategy processes
- **Deployment docs** — repo map, heartbeat contract, watchdog usage
- **Shared helpers** — legacy `env_loader.py`, `node_bridge.py` used when strategies run under the local `Core Strategy/` layout

## What does not live here

Each strategy worker has its own repository with vendored `strategy_heartbeat.py` and strategy-specific code:

| Code | Repository |
|------|------------|
| S1 on-chain radar | [onChain-radar](https://github.com/golddemon422/onChain-radar) |
| S2 Binance Alpha | [binance-alpha-monitor](https://github.com/golddemon422/binance-alpha-monitor) |
| S3 OI / funding | [OI_Funding_rate_scaner](https://github.com/golddemon422/OI_Funding_rate_scaner) |
| S4 AI trading | [Ai-Trading](https://github.com/golddemon422/Ai-Trading) |
| S5 heat radar | [accumulation-fastsignal-radar](https://github.com/golddemon422/accumulation-fastsignal-radar) |
| S6 accumulation | [accumulation-radar](https://github.com/golddemon422/accumulation-radar) |

Monitoring UI and API:

- [Web3-MonitoringBacked](https://github.com/golddemon422/Web3-MonitoringBacked)
- [Web3-MonitoringTools](https://github.com/golddemon422/Web3-MonitoringTools)

See [docs/strategy-repo-map.md](docs/strategy-repo-map.md) for branches and local layout notes.

## Local runtime layout (Windows)

Production-style local layout under `D:\Web3Tools`:

```
D:\Web3Tools\
  Core Strategy\          # live runtime (nested strategy clones, run-state, run-logs)
  launchers\              # operational copy of launcher/watchdog scripts
  Core-Strategy-Orchestration\   # this repo (versioned orchestration)
  Web3-MonitoringBacked\
  Web3-MonitoringTools\
```

The watchdog reads heartbeat files from `Core Strategy/run-state/` and PID files from `launchers/pids/`. Paths are configured for this layout in `launchers/strategy_watchdog.py`.

## Quick start — watchdog (Phase 2A dry-run)

```powershell
python launchers/strategy_watchdog.py --once
```

See [docs/watchdog.md](docs/watchdog.md) for full usage and exit codes.
