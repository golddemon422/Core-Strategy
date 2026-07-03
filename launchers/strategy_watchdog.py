#!/usr/bin/env python3
"""
Phase 2A strategy watchdog — dry-run only.

Checks S1–S6 heartbeat files and PID files, reports what would be done.
Never restarts or kills processes in this phase.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Decision = Literal["ok", "would_warn", "would_restart"]
Status = Literal[
    "healthy",
    "sleeping_ok",
    "idle",
    "stale",
    "offline",
    "missing_heartbeat",
    "invalid_heartbeat",
    "process_stopped",
    "heartbeat_error",
    "phase_overdue",
    "business_api_fail",
    "business_sla_stale",
    "business_scan_stale",
]

REPO_ROOT = Path(r"D:\Web3Tools")
CORE_STRATEGY = REPO_ROOT / "Core Strategy"
DEFAULT_STATE_DIR = CORE_STRATEGY / "run-state"
DEFAULT_PID_DIR = REPO_ROOT / "launchers" / "pids"
DEFAULT_LOG_DIR = CORE_STRATEGY / "run-logs"
DEFAULT_REPORT_PATH = DEFAULT_STATE_DIR / "watchdog-report.json"
DEFAULT_LOG_PATH = DEFAULT_LOG_DIR / "strategy_watchdog.log"
LAUNCHER_PS1 = REPO_ROOT / "launchers" / "launch_strategy.ps1"

ERROR_RESTART_MIN_COUNT = 3
ERROR_RESTART_RECENT_SEC = 300
BUSINESS_SLA_STRATEGIES = frozenset({"S5", "S6"})
BUSINESS_INTERVAL_SEC = 1800
BUSINESS_STALE_MULTIPLIER = 2


@dataclass(frozen=True)
class StrategyWatchdogConfig:
    worker: str
    stale_after_sec: int
    offline_after_sec: int
    stale_action: Decision = "would_restart"
    offline_action: Decision = "would_restart"
    phase_overdue_action: Decision = "would_warn"
    respect_sleep_schedule: bool = False
    max_phase_sec: dict[str, int] = field(default_factory=dict)
    phase_overdue_requires_stale: bool = False


STRATEGY_CONFIG: dict[str, StrategyWatchdogConfig] = {
    "S1": StrategyWatchdogConfig(
        worker="onchain_narrative_radar",
        stale_after_sec=180,
        offline_after_sec=600,
        max_phase_sec={"scan": 3600, "sleep": 300},
        phase_overdue_requires_stale=True,
    ),
    "S2": StrategyWatchdogConfig(
        worker="binance_alpha_monitor",
        stale_after_sec=180,
        offline_after_sec=600,
    ),
    "S3": StrategyWatchdogConfig(
        worker="oi_funding_scanner",
        stale_after_sec=900,
        offline_after_sec=1800,
        respect_sleep_schedule=True,
    ),
    "S4": StrategyWatchdogConfig(
        worker="futures_alpha_scanner",
        stale_after_sec=300,
        offline_after_sec=900,
    ),
    "S5": StrategyWatchdogConfig(
        worker="heat_radar",
        stale_after_sec=2700,
        offline_after_sec=5400,
        respect_sleep_schedule=True,
    ),
    "S6": StrategyWatchdogConfig(
        worker="accumulation_radar",
        stale_after_sec=2700,
        offline_after_sec=7200,
        stale_action="would_warn",
        offline_action="would_restart",
        phase_overdue_requires_stale=True,
    ),
}


@dataclass
class StrategyCheckResult:
    strategy: str
    worker: str
    pid_file_pid: int | None
    heartbeat_pid: int | None
    process_alive: bool | None
    heartbeat_age_sec: float | None
    status: Status
    phase: str | None
    next_run_at: str | None
    decision: Decision
    reason: str
    dry_run: bool = True
    would_restart_command: str | None = None
    business_status: str | None = None
    business_reason: str | None = None
    last_scan_outcome: str | None = None
    last_scan_completed_at: str | None = None
    last_telegram_sent_at: str | None = None
    consecutive_scan_failures: int | None = None
    last_api_error_at: str | None = None

    def to_row(self) -> dict[str, Any]:
        row = {
            "strategy": self.strategy,
            "worker": self.worker,
            "pid_file_pid": self.pid_file_pid,
            "heartbeat_pid": self.heartbeat_pid,
            "process_alive": self.process_alive,
            "heartbeat_age_sec": round(self.heartbeat_age_sec, 1) if self.heartbeat_age_sec is not None else None,
            "status": self.status,
            "phase": self.phase,
            "nextRunAt": self.next_run_at,
            "decision": self.decision,
            "reason": self.reason,
        }
        if self.strategy in BUSINESS_SLA_STRATEGIES:
            row["businessStatus"] = self.business_status
            row["businessReason"] = self.business_reason
            row["lastScanOutcome"] = self.last_scan_outcome
            row["lastScanCompletedAt"] = self.last_scan_completed_at
            row["lastTelegramSentAt"] = self.last_telegram_sent_at
            row["consecutiveScanFailures"] = self.consecutive_scan_failures
            row["lastApiErrorAt"] = self.last_api_error_at
        return row


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(iso: str | None) -> datetime | None:
    if not iso or not isinstance(iso, str):
        return None
    text = iso.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_sec(iso: str | None, now: datetime) -> float | None:
    dt = _parse_iso(iso)
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds())


def _restart_command(strategy: str) -> str:
    return (
        f'powershell -NoProfile -ExecutionPolicy Bypass -File "{LAUNCHER_PS1}" '
        f"-Strategy {strategy} -Force"
    )


def _populate_business_fields(result: StrategyCheckResult, hb: dict[str, Any]) -> None:
    result.last_scan_outcome = hb.get("lastScanOutcome") if isinstance(hb.get("lastScanOutcome"), str) else None
    result.last_scan_completed_at = (
        hb.get("lastScanCompletedAt") if isinstance(hb.get("lastScanCompletedAt"), str) else None
    )
    result.last_telegram_sent_at = (
        hb.get("lastTelegramSentAt") if isinstance(hb.get("lastTelegramSentAt"), str) else None
    )
    consec = hb.get("consecutiveScanFailures")
    result.consecutive_scan_failures = int(consec) if isinstance(consec, int) else None
    result.last_api_error_at = hb.get("lastApiErrorAt") if isinstance(hb.get("lastApiErrorAt"), str) else None


def _evaluate_business_sla(
    strategy: str,
    hb: dict[str, Any],
    now: datetime,
    base: StrategyCheckResult,
) -> StrategyCheckResult:
    if strategy not in BUSINESS_SLA_STRATEGIES:
        return base

    _populate_business_fields(base, hb)
    expected = hb.get("expectedIntervalSec")
    interval = int(expected) if isinstance(expected, int) and expected > 0 else BUSINESS_INTERVAL_SEC
    stale_limit = interval * BUSINESS_STALE_MULTIPLIER

    warn_reasons: list[str] = []
    business_status: Status | None = None

    outcome = base.last_scan_outcome
    consec = base.consecutive_scan_failures
    if outcome == "binance_api_fail" and isinstance(consec, int) and consec >= 2:
        business_status = "business_api_fail"
        warn_reasons.append(f"consecutive Binance API failures ({consec})")

    if base.last_telegram_sent_at:
        tg_age = _age_sec(base.last_telegram_sent_at, now)
        if tg_age is not None and tg_age > stale_limit:
            if business_status is None:
                business_status = "business_sla_stale"
            warn_reasons.append(
                f"no Futures Radar Telegram send for >2 intervals ({int(tg_age)}s > {stale_limit}s)"
            )

    if base.last_scan_completed_at:
        scan_age = _age_sec(base.last_scan_completed_at, now)
        if scan_age is not None and scan_age > stale_limit:
            if business_status is None:
                business_status = "business_scan_stale"
            warn_reasons.append(
                f"no successful scan completion for >2 intervals ({int(scan_age)}s > {stale_limit}s)"
            )

    if warn_reasons:
        base.decision = max_decision(base.decision, "would_warn")
        if business_status is not None:
            base.status = business_status
        base.business_status = business_status
        base.business_reason = "; ".join(warn_reasons)
        if base.decision == "would_warn" and base.reason and "Binance API" not in base.reason:
            base.reason = f"{base.business_reason}; process: {base.reason}"
        elif base.decision == "would_warn":
            base.reason = base.business_reason
    else:
        base.business_status = "ok"
        base.business_reason = None

    return base


def _finalize_result(
    strategy: str,
    hb: dict[str, Any] | None,
    now: datetime,
    result: StrategyCheckResult,
) -> StrategyCheckResult:
    if hb is not None and strategy in BUSINESS_SLA_STRATEGIES:
        return _evaluate_business_sla(strategy, hb, now, result)
    return result


def read_pid_file(path: Path) -> int | None:
    try:
        if not path.is_file():
            return None
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        token = raw.split()[0]
        pid = int(token)
        return pid if pid > 0 else None
    except (OSError, ValueError):
        return None


def _is_process_alive_psutil(pid: int) -> bool | None:
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        return psutil.pid_exists(pid)
    except Exception:
        return False


def _is_process_alive_tasklist(pid: int) -> bool | None:
    if sys.platform != "win32":
        return None
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if str(pid) in out and "No tasks" not in out:
            return True
        return False
    except (OSError, subprocess.SubprocessError):
        return None


def _is_process_alive_os_kill(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


def is_process_alive(pid: int | None) -> bool | None:
    if pid is None:
        return None
    alive = _is_process_alive_psutil(pid)
    if alive is not None:
        return alive
    alive = _is_process_alive_tasklist(pid)
    if alive is not None:
        return alive
    return _is_process_alive_os_kill(pid)


def read_heartbeat_file(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Return (parsed_json_or_none, error_reason_or_none)."""
    if not path.is_file():
        return None, "missing"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"read_error:{exc.__class__.__name__}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(data, dict):
        return None, "invalid_shape"
    return data, None


def _is_future_iso(iso: str | None, now: datetime) -> bool:
    dt = _parse_iso(iso)
    if dt is None:
        return False
    return dt > now


def _error_decision(hb: dict[str, Any], now: datetime) -> tuple[Decision, str]:
    error_count = hb.get("errorCount")
    last_error_at = hb.get("lastErrorAt")
    if isinstance(error_count, int) and error_count >= ERROR_RESTART_MIN_COUNT:
        return "would_restart", f"heartbeat error status with errorCount={error_count}"
    err_age = _age_sec(last_error_at if isinstance(last_error_at, str) else None, now)
    if (
        isinstance(error_count, int)
        and error_count > 1
        and err_age is not None
        and err_age <= ERROR_RESTART_RECENT_SEC
    ):
        return "would_restart", "recent repeated heartbeat errors"
    return "would_warn", "heartbeat status is error"


def _in_tolerated_long_phase(
    hb: dict[str, Any],
    cfg: StrategyWatchdogConfig,
    now: datetime,
) -> tuple[bool, str | None]:
    if not cfg.max_phase_sec:
        return False, None
    if str(hb.get("status") or "") != "running":
        return False, None
    phase = str(hb.get("phase") or "")
    limit = cfg.max_phase_sec.get(phase)
    if limit is None:
        return False, None
    phase_age = _age_sec(
        hb.get("lastLoopStartedAt") if isinstance(hb.get("lastLoopStartedAt"), str) else None,
        now,
    )
    if phase_age is None or phase_age > limit:
        return False, None
    return True, f"running phase {phase!r} for {int(phase_age)}s (limit {limit}s)"


def _apply_long_phase_stale_cap(
    decision: Decision,
    cfg: StrategyWatchdogConfig,
    hb: dict[str, Any],
    now: datetime,
) -> tuple[Decision, str | None]:
    if decision not in {"would_restart", "would_warn"}:
        return decision, None
    if not cfg.phase_overdue_requires_stale:
        return decision, None
    ok, detail = _in_tolerated_long_phase(hb, cfg, now)
    if not ok:
        return decision, None
    if decision == "would_restart":
        return "would_warn", detail
    return decision, detail


def _phase_overdue(
    hb: dict[str, Any],
    cfg: StrategyWatchdogConfig,
    now: datetime,
    heartbeat_age: float | None,
) -> tuple[bool, str | None]:
    if not cfg.max_phase_sec:
        return False, None
    status = str(hb.get("status") or "")
    if status != "running":
        return False, None
    phase = str(hb.get("phase") or "")
    limit = cfg.max_phase_sec.get(phase)
    if limit is None:
        return False, None
    phase_age = _age_sec(hb.get("lastLoopStartedAt") if isinstance(hb.get("lastLoopStartedAt"), str) else None, now)
    if phase_age is None:
        return False, None
    if phase_age <= limit:
        return False, None
    if cfg.phase_overdue_requires_stale and heartbeat_age is not None and heartbeat_age <= cfg.stale_after_sec:
        return True, f"phase {phase!r} running {int(phase_age)}s > {limit}s (heartbeat still fresh)"
    if phase_age > limit:
        return True, f"phase {phase!r} running {int(phase_age)}s > {limit}s"
    return False, None


def evaluate_strategy(
    strategy: str,
    *,
    state_dir: Path,
    pid_dir: Path,
    now: datetime | None = None,
    dry_run: bool = True,
) -> StrategyCheckResult:
    cfg = STRATEGY_CONFIG[strategy]
    now = now or _utc_now()
    hb_path = state_dir / f"{strategy}.heartbeat.json"
    pid_path = pid_dir / f"{strategy}.pid"

    pid_file_pid = read_pid_file(pid_path)
    process_alive = is_process_alive(pid_file_pid)

    base = StrategyCheckResult(
        strategy=strategy,
        worker=cfg.worker,
        pid_file_pid=pid_file_pid,
        heartbeat_pid=None,
        process_alive=process_alive,
        heartbeat_age_sec=None,
        status="healthy",
        phase=None,
        next_run_at=None,
        decision="ok",
        reason="",
        dry_run=dry_run,
        would_restart_command=_restart_command(strategy),
    )
    hb: dict[str, Any] | None = None

    if pid_file_pid is not None and process_alive is False:
        base.status = "process_stopped"
        base.decision = "would_restart"
        base.reason = f"PID file {pid_file_pid} is not a running process"
        return _finalize_result(strategy, hb, now, base)

    hb, hb_err = read_heartbeat_file(hb_path)
    if hb_err == "missing":
        base.status = "missing_heartbeat"
        if process_alive is True:
            base.decision = "would_warn"
            base.reason = "heartbeat file missing but launcher PID process is alive"
        else:
            base.decision = "would_restart"
            base.reason = "heartbeat file missing and no alive launcher process"
        return _finalize_result(strategy, hb, now, base)

    if hb is None:
        base.status = "invalid_heartbeat"
        base.decision = "would_warn"
        base.reason = f"heartbeat file unreadable ({hb_err})"
        return _finalize_result(strategy, hb, now, base)

    hb_status = str(hb.get("status") or "")
    hb_phase = str(hb.get("phase") or "") or None
    next_run_at = hb.get("nextRunAt") if isinstance(hb.get("nextRunAt"), str) else None
    hb_pid_raw = hb.get("pid")
    heartbeat_pid = int(hb_pid_raw) if isinstance(hb_pid_raw, int) and hb_pid_raw > 0 else None
    heartbeat_age = _age_sec(hb.get("lastHeartbeatAt") if isinstance(hb.get("lastHeartbeatAt"), str) else None, now)

    base.heartbeat_pid = heartbeat_pid
    base.heartbeat_age_sec = heartbeat_age
    base.phase = hb_phase
    base.next_run_at = next_run_at

    if heartbeat_pid is not None and process_alive is not True:
        hb_alive = is_process_alive(heartbeat_pid)
        if hb_alive is False:
            base.status = "process_stopped"
            base.decision = "would_restart"
            base.reason = f"heartbeat pid {heartbeat_pid} is not running"
            return _finalize_result(strategy, hb, now, base)

    if hb_status == "error":
        decision, reason = _error_decision(hb, now)
        base.status = "heartbeat_error"
        base.decision = decision
        base.reason = reason
        return _finalize_result(strategy, hb, now, base)

    if cfg.respect_sleep_schedule and hb_status == "sleeping" and _is_future_iso(next_run_at, now):
        base.status = "sleeping_ok"
        base.decision = "ok"
        base.reason = "sleeping with nextRunAt in the future"
        return _finalize_result(strategy, hb, now, base)

    if hb_status == "sleeping" and _is_future_iso(next_run_at, now):
        base.status = "sleeping_ok"
        base.decision = "ok"
        base.reason = "sleeping with nextRunAt in the future"
        return _finalize_result(strategy, hb, now, base)

    if heartbeat_age is not None and heartbeat_age <= cfg.stale_after_sec:
        overdue, overdue_reason = _phase_overdue(hb, cfg, now, heartbeat_age)
        if overdue and overdue_reason:
            base.status = "phase_overdue"
            if cfg.phase_overdue_requires_stale:
                base.decision = cfg.phase_overdue_action
                base.reason = overdue_reason + " (heartbeat fresh; warn only)"
            else:
                base.decision = cfg.phase_overdue_action
                base.reason = overdue_reason
            return _finalize_result(strategy, hb, now, base)

        if hb_phase == "idle" or hb_status == "idle":
            base.status = "idle"
            base.decision = "ok"
            base.reason = "heartbeat fresh and idle"
            return _finalize_result(strategy, hb, now, base)

        base.status = "healthy"
        base.decision = "ok"
        base.reason = f"heartbeat age {int(heartbeat_age)}s <= stale threshold {cfg.stale_after_sec}s"
        return _finalize_result(strategy, hb, now, base)

    overdue, overdue_reason = _phase_overdue(hb, cfg, now, heartbeat_age)
    if overdue and overdue_reason:
        base.status = "phase_overdue"
        if cfg.phase_overdue_requires_stale and heartbeat_age is not None and heartbeat_age <= cfg.stale_after_sec:
            base.decision = cfg.phase_overdue_action
            base.reason = overdue_reason + " (heartbeat fresh; warn only)"
        else:
            base.decision = max_decision(cfg.phase_overdue_action, _age_decision(cfg, heartbeat_age))
            base.reason = overdue_reason
        return _finalize_result(strategy, hb, now, base)

    if heartbeat_age is None:
        base.status = "invalid_heartbeat"
        base.decision = "would_warn"
        base.reason = "missing or unparseable lastHeartbeatAt"
        return _finalize_result(strategy, hb, now, base)

    if heartbeat_age <= cfg.offline_after_sec:
        base.status = "stale"
        decision = cfg.stale_action
        cap_decision, cap_detail = _apply_long_phase_stale_cap(decision, cfg, hb, now)
        base.decision = cap_decision
        base.reason = (
            f"heartbeat age {int(heartbeat_age)}s > stale {cfg.stale_after_sec}s "
            f"and <= offline {cfg.offline_after_sec}s"
        )
        if cap_detail:
            base.reason += f"; {cap_detail} (warn only during long phase)"
        return _finalize_result(strategy, hb, now, base)

    base.status = "offline"
    decision = cfg.offline_action
    cap_decision, cap_detail = _apply_long_phase_stale_cap(decision, cfg, hb, now)
    base.decision = cap_decision
    base.reason = f"heartbeat age {int(heartbeat_age)}s > offline threshold {cfg.offline_after_sec}s"
    if cap_detail:
        base.reason += f"; {cap_detail} (warn only during long phase)"
    return _finalize_result(strategy, hb, now, base)


def _age_decision(cfg: StrategyWatchdogConfig, heartbeat_age: float | None) -> Decision:
    if heartbeat_age is None:
        return "would_warn"
    if heartbeat_age <= cfg.offline_after_sec:
        return cfg.stale_action
    return cfg.offline_action


def max_decision(a: Decision, b: Decision) -> Decision:
    order = {"ok": 0, "would_warn": 1, "would_restart": 2}
    return a if order[a] >= order[b] else b


def run_watchdog(
    *,
    strategies: list[str] | None = None,
    state_dir: Path = DEFAULT_STATE_DIR,
    pid_dir: Path = DEFAULT_PID_DIR,
    report_path: Path = DEFAULT_REPORT_PATH,
    log_path: Path = DEFAULT_LOG_PATH,
    dry_run: bool = True,
    verbose: bool = False,
) -> tuple[list[StrategyCheckResult], int]:
    targets = strategies or list(STRATEGY_CONFIG.keys())
    now = _utc_now()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("strategy_watchdog")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    if verbose:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(console)

    results: list[StrategyCheckResult] = []
    for strategy in targets:
        if strategy not in STRATEGY_CONFIG:
            logger.warning("unknown strategy %s skipped", strategy)
            continue
        result = evaluate_strategy(strategy, state_dir=state_dir, pid_dir=pid_dir, now=now, dry_run=dry_run)
        results.append(result)
        logger.info(
            "%s status=%s decision=%s reason=%s",
            strategy,
            result.status,
            result.decision,
            result.reason,
        )

    exit_code = compute_exit_code(results)
    report = {
        "generatedAt": now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "dryRun": dry_run,
        "exitCode": exit_code,
        "strategies": [r.to_row() for r in results],
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results if r.decision == "ok"),
            "would_warn": sum(1 for r in results if r.decision == "would_warn"),
            "would_restart": sum(1 for r in results if r.decision == "would_restart"),
        },
    }
    for r in results:
        if r.decision != "ok":
            report.setdefault("actions", []).append(
                {
                    "strategy": r.strategy,
                    "decision": r.decision,
                    "command": r.would_restart_command if r.decision == "would_restart" else None,
                    "reason": r.reason,
                }
            )

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("report written to %s (exit=%s)", report_path, exit_code)
    return results, exit_code


def compute_exit_code(results: list[StrategyCheckResult]) -> int:
    if any(r.decision == "would_restart" for r in results):
        return 2
    if any(r.decision == "would_warn" for r in results):
        return 1
    return 0


def format_table(results: list[StrategyCheckResult]) -> str:
    headers = [
        "strategy",
        "worker",
        "pid_file",
        "hb_pid",
        "alive",
        "hb_age",
        "status",
        "phase",
        "nextRunAt",
        "decision",
        "reason",
    ]
    rows: list[list[str]] = []
    for r in results:
        age = "" if r.heartbeat_age_sec is None else f"{r.heartbeat_age_sec:.0f}s"
        alive = "" if r.process_alive is None else ("yes" if r.process_alive else "no")
        rows.append(
            [
                r.strategy,
                r.worker,
                str(r.pid_file_pid or ""),
                str(r.heartbeat_pid or ""),
                alive,
                age,
                r.status,
                r.phase or "",
                (r.next_run_at or "")[:19],
                r.decision,
                r.reason[:60] + ("…" if len(r.reason) > 60 else ""),
            ]
        )

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells))

    lines = [fmt_row(headers), fmt_row(["-" * w for w in widths])]
    lines.extend(fmt_row(row) for row in rows)
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 2A strategy watchdog (dry-run only)")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between checks (loop mode)")
    parser.add_argument(
        "--dry-run",
        default="true",
        choices=["true", "false"],
        help="Dry-run mode (default true; false is not implemented in Phase 2A)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    parser.add_argument("--strategy", type=str, help="Check a single strategy (e.g. S3)")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging to console")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--pid-dir", type=Path, default=DEFAULT_PID_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run.lower() != "true":
        print("Phase 2A only supports --dry-run true", file=sys.stderr)
        return 2

    strategies = None
    if args.strategy:
        strategies = [args.strategy.strip().upper()]

    def cycle() -> int:
        results, exit_code = run_watchdog(
            strategies=strategies,
            state_dir=args.state_dir,
            pid_dir=args.pid_dir,
            report_path=args.report_path,
            log_path=args.log_path,
            dry_run=True,
            verbose=args.verbose,
        )
        if args.json:
            print(json.dumps([r.to_row() for r in results], ensure_ascii=False, indent=2))
        else:
            print(format_table(results))
            print(f"\nreport: {args.report_path}")
            print(f"log:    {args.log_path}")
            print(f"exit:   {exit_code} (dry-run — no restarts performed)")
        return exit_code

    if args.once or args.interval <= 0:
        return cycle()

    while True:
        code = cycle()
        if code != 0 and args.verbose:
            print(f"watchdog cycle exit code {code}", file=sys.stderr)
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
