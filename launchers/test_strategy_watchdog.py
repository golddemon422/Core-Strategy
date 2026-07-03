#!/usr/bin/env python3
"""Offline tests for strategy_watchdog.py — uses temp fixtures only."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_LAUNCHERS = Path(__file__).resolve().parent
if str(_LAUNCHERS) not in sys.path:
    sys.path.insert(0, str(_LAUNCHERS))

from strategy_watchdog import (  # noqa: E402
    Decision,
    ExecuteConfig,
    RestartHistoryStore,
    assign_baseline_actions,
    evaluate_strategy,
    compute_exit_code,
    execute_restart_phase,
    read_heartbeat_file,
    read_pid_file,
    run_watchdog,
    select_restart_candidate,
    verify_post_restart,
    StrategyCheckResult,
)


def _iso_offset(sec: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _iso_ago(sec: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _write_hb(state: Path, strategy: str, payload: dict) -> None:
    path = state / f"{strategy}.heartbeat.json"
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def _base_hb(strategy: str = "S2", worker: str = "binance_alpha_monitor", **overrides) -> dict:
    data = {
        "strategy": strategy,
        "worker": worker,
        "pid": os.getpid(),
        "status": "running",
        "phase": "scan",
        "lastHeartbeatAt": _iso_ago(30),
        "lastLoopStartedAt": _iso_ago(60),
        "nextRunAt": None,
        "errorCount": 0,
        "lastErrorAt": None,
    }
    data.update(overrides)
    return data


class StrategyWatchdogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._tmp.name) / "run-state"
        self.pid_dir = Path(self._tmp.name) / "pids"
        self.state_dir.mkdir(parents=True)
        self.pid_dir.mkdir(parents=True)
        self.now = datetime.now(timezone.utc)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _eval(self, strategy: str = "S2") -> StrategyCheckResult:
        return evaluate_strategy(
            strategy,
            state_dir=self.state_dir,
            pid_dir=self.pid_dir,
            now=self.now,
            dry_run=True,
        )

    def test_fresh_heartbeat_ok(self) -> None:
        _write_hb(self.state_dir, "S2", _base_hb())
        r = self._eval("S2")
        self.assertEqual(r.decision, "ok")
        self.assertEqual(r.status, "healthy")

    def test_sleeping_next_run_future_ok(self) -> None:
        _write_hb(
            self.state_dir,
            "S3",
            _base_hb(
                strategy="S3",
                worker="oi_funding_scanner",
                status="sleeping",
                phase="sleep",
                lastHeartbeatAt=_iso_ago(120),
                nextRunAt=_iso_offset(3600),
            ),
        )
        r = self._eval("S3")
        self.assertEqual(r.decision, "ok")
        self.assertEqual(r.status, "sleeping_ok")

    def test_s1_long_scan_stale_capped_to_warn(self) -> None:
        _write_hb(
            self.state_dir,
            "S1",
            _base_hb(
                strategy="S1",
                worker="onchain_narrative_radar",
                lastHeartbeatAt=_iso_ago(500),
                lastLoopStartedAt=_iso_ago(500),
                status="running",
                phase="scan",
            ),
        )
        r = self._eval("S1")
        self.assertEqual(r.status, "stale")
        self.assertEqual(r.decision, "would_warn")

        _write_hb(
            self.state_dir,
            "S2",
            _base_hb(lastHeartbeatAt=_iso_ago(400), status="running", phase="scan"),
        )
        r = self._eval("S2")
        self.assertEqual(r.status, "stale")
        self.assertEqual(r.decision, "would_restart")

    def test_stale_heartbeat_would_warn_s6(self) -> None:
        _write_hb(
            self.state_dir,
            "S6",
            _base_hb(
                strategy="S6",
                worker="accumulation_radar",
                lastHeartbeatAt=_iso_ago(3000),
                status="running",
                phase="pool",
            ),
        )
        r = self._eval("S6")
        self.assertEqual(r.status, "stale")
        self.assertEqual(r.decision, "would_warn")

    def test_offline_heartbeat_would_restart_s6(self) -> None:
        _write_hb(
            self.state_dir,
            "S6",
            _base_hb(
                strategy="S6",
                worker="accumulation_radar",
                lastHeartbeatAt=_iso_ago(8000),
                status="running",
                phase="pool",
            ),
        )
        r = self._eval("S6")
        self.assertEqual(r.status, "offline")
        self.assertEqual(r.decision, "would_restart")

    def test_missing_heartbeat_no_process_would_restart(self) -> None:
        r = self._eval("S2")
        self.assertEqual(r.status, "missing_heartbeat")
        self.assertEqual(r.decision, "would_restart")

    def test_missing_heartbeat_alive_pid_would_warn(self) -> None:
        (self.pid_dir / "S2.pid").write_text(f"{__import__('os').getpid()}\n", encoding="utf-8")
        r = self._eval("S2")
        self.assertEqual(r.status, "missing_heartbeat")
        self.assertEqual(r.decision, "would_warn")

    def test_invalid_heartbeat_would_warn(self) -> None:
        path = self.state_dir / "S2.heartbeat.json"
        path.write_text("{not json", encoding="utf-8")
        parsed, err = read_heartbeat_file(path)
        self.assertIsNone(parsed)
        self.assertEqual(err, "invalid_json")
        r = self._eval("S2")
        self.assertEqual(r.status, "invalid_heartbeat")
        self.assertEqual(r.decision, "would_warn")

    def test_stopped_process_would_restart(self) -> None:
        _write_hb(
            self.state_dir,
            "S2",
            _base_hb(pid=999999, lastHeartbeatAt=_iso_ago(400)),
        )
        (self.pid_dir / "S2.pid").write_text("999999\n", encoding="utf-8")
        r = self._eval("S2")
        self.assertEqual(r.decision, "would_restart")
        self.assertIn(r.status, ("process_stopped", "stale", "offline"))

    def test_exit_codes(self) -> None:
        ok = StrategyCheckResult(
            strategy="S1",
            worker="w",
            pid_file_pid=None,
            heartbeat_pid=None,
            process_alive=None,
            heartbeat_age_sec=1,
            status="healthy",
            phase="scan",
            next_run_at=None,
            decision="ok",
            reason="",
        )
        warn = StrategyCheckResult(
            strategy="S6",
            worker="w",
            pid_file_pid=None,
            heartbeat_pid=None,
            process_alive=None,
            heartbeat_age_sec=1,
            status="stale",
            phase="scan",
            next_run_at=None,
            decision="would_warn",
            reason="",
        )
        restart = StrategyCheckResult(
            strategy="S2",
            worker="w",
            pid_file_pid=None,
            heartbeat_pid=None,
            process_alive=None,
            heartbeat_age_sec=1,
            status="offline",
            phase="scan",
            next_run_at=None,
            decision="would_restart",
            reason="",
        )
        self.assertEqual(compute_exit_code([ok]), 0)
        self.assertEqual(compute_exit_code([ok, warn]), 1)
        self.assertEqual(compute_exit_code([ok, warn, restart]), 2)

    def test_s5_fresh_heartbeat_recent_tg_ok(self) -> None:
        _write_hb(
            self.state_dir,
            "S5",
            _base_hb(
                strategy="S5",
                worker="heat_radar",
                status="sleeping",
                phase="sleep",
                lastHeartbeatAt=_iso_ago(60),
                nextRunAt=_iso_offset(1700),
                lastScanOutcome="ok",
                lastScanCompletedAt=_iso_ago(600),
                lastTelegramSentAt=_iso_ago(600),
                consecutiveScanFailures=0,
                expectedIntervalSec=1800,
            ),
        )
        r = self._eval("S5")
        self.assertEqual(r.decision, "ok")
        self.assertIn(r.status, ("sleeping_ok", "healthy"))

    def test_s5_sleeping_stale_telegram_would_warn(self) -> None:
        _write_hb(
            self.state_dir,
            "S5",
            _base_hb(
                strategy="S5",
                worker="heat_radar",
                status="sleeping",
                phase="sleep",
                lastHeartbeatAt=_iso_ago(30),
                nextRunAt=_iso_offset(1700),
                lastScanOutcome="binance_api_fail",
                lastScanCompletedAt=_iso_ago(4000),
                lastTelegramSentAt=_iso_ago(4000),
                consecutiveScanFailures=1,
                expectedIntervalSec=1800,
            ),
        )
        r = self._eval("S5")
        self.assertEqual(r.decision, "would_warn")
        self.assertEqual(r.status, "business_sla_stale")

    def test_s6_consecutive_api_fail_would_warn(self) -> None:
        _write_hb(
            self.state_dir,
            "S6",
            _base_hb(
                strategy="S6",
                worker="accumulation_radar",
                status="sleeping",
                phase="sleep",
                lastHeartbeatAt=_iso_ago(45),
                nextRunAt=_iso_offset(1700),
                lastScanOutcome="binance_api_fail",
                lastScanCompletedAt=_iso_ago(500),
                lastTelegramSentAt=_iso_ago(500),
                consecutiveScanFailures=2,
                lastApiErrorAt=_iso_ago(60),
                expectedIntervalSec=1800,
            ),
        )
        r = self._eval("S6")
        self.assertEqual(r.decision, "would_warn")
        self.assertEqual(r.status, "business_api_fail")

    def test_s6_stale_scan_fresh_heartbeat_would_warn(self) -> None:
        _write_hb(
            self.state_dir,
            "S6",
            _base_hb(
                strategy="S6",
                worker="accumulation_radar",
                status="healthy",
                phase="idle",
                lastHeartbeatAt=_iso_ago(20),
                lastScanOutcome="ok",
                lastScanCompletedAt=_iso_ago(4000),
                lastTelegramSentAt=_iso_ago(500),
                consecutiveScanFailures=0,
                expectedIntervalSec=1800,
            ),
        )
        r = self._eval("S6")
        self.assertEqual(r.decision, "would_warn")
        self.assertEqual(r.status, "business_scan_stale")

    def test_s3_sleeping_future_next_run_still_ok(self) -> None:
        _write_hb(
            self.state_dir,
            "S3",
            _base_hb(
                strategy="S3",
                worker="oi_funding_scanner",
                status="sleeping",
                phase="sleep",
                lastHeartbeatAt=_iso_ago(120),
                nextRunAt=_iso_offset(3600),
            ),
        )
        r = self._eval("S3")
        self.assertEqual(r.decision, "ok")
        self.assertEqual(r.status, "sleeping_ok")


class ExecuteModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._tmp.name) / "run-state"
        self.pid_dir = Path(self._tmp.name) / "pids"
        self.history_path = self.state_dir / "watchdog-restart-history.json"
        self.report_path = self.state_dir / "watchdog-report.json"
        self.log_path = Path(self._tmp.name) / "logs" / "watchdog.log"
        self.state_dir.mkdir(parents=True)
        self.pid_dir.mkdir(parents=True)
        self.log_path.parent.mkdir(parents=True)
        self.now = datetime.now(timezone.utc)
        self.launch_calls: list[str] = []

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_offline_hb(self, strategy: str, worker: str, age_sec: float = 8000) -> None:
        _write_hb(
            self.state_dir,
            strategy,
            _base_hb(
                strategy=strategy,
                worker=worker,
                lastHeartbeatAt=_iso_ago(age_sec),
                status="running",
                phase="scan",
            ),
        )

    def _mock_launch(self, strategy: str, _launcher: Path) -> tuple[int, str]:
        self.launch_calls.append(strategy)
        pid_file = self.pid_dir / f"{strategy}.pid"
        pid_file.write_text("424242\n", encoding="utf-8")
        cfg_worker = {
            "S1": "onchain_narrative_radar",
            "S2": "binance_alpha_monitor",
            "S3": "oi_funding_scanner",
            "S4": "futures_alpha_scanner",
            "S5": "heat_radar",
            "S6": "accumulation_radar",
        }[strategy]
        hb = _base_hb(
            strategy=strategy,
            worker=cfg_worker,
            pid=424242,
            lastHeartbeatAt=_iso_now(datetime.now(timezone.utc) + timedelta(seconds=2)),
            status="running",
            phase="scan",
        )
        _write_hb(self.state_dir, strategy, hb)
        return 0, "ok"

    def _exec_config(self, **kwargs) -> ExecuteConfig:
        base = {
            "restart_history_path": self.history_path,
            "launcher_ps1": Path("/fake/launch_strategy.ps1"),
            "verify_timeout_sec": 2,
            "verify_interval_sec": 0,
            "launch_fn": self._mock_launch,
            "verify_pid_fn": lambda _s, _p: True,
            "is_process_alive_fn": lambda pid: True if pid == 424242 else False,
            "sleep_fn": lambda _s: None,
        }
        base.update(kwargs)
        return ExecuteConfig(**base)

    def _run(self, *, dry_run: bool = True, strategies: list[str] | None = None, **exec_kw) -> list[StrategyCheckResult]:
        cfg = self._exec_config(**exec_kw)
        if strategies and len(strategies) == 1:
            cfg = ExecuteConfig(**{**cfg.__dict__, "explicit_strategy": strategies[0]})
        results, _ = run_watchdog(
            strategies=strategies,
            state_dir=self.state_dir,
            pid_dir=self.pid_dir,
            report_path=self.report_path,
            log_path=self.log_path,
            dry_run=dry_run,
            execute_config=cfg,
        )
        return results

    def _run_strategies(self, strategies: list[str], *, dry_run: bool = False, **exec_kw) -> list[StrategyCheckResult]:
        cfg = self._exec_config(**exec_kw)
        results, _ = run_watchdog(
            strategies=strategies,
            state_dir=self.state_dir,
            pid_dir=self.pid_dir,
            report_path=self.report_path,
            log_path=self.log_path,
            dry_run=dry_run,
            execute_config=cfg,
        )
        return results

    def test_default_dry_run_never_restarts(self) -> None:
        self._write_offline_hb("S2", "binance_alpha_monitor", 400)
        results = self._run(dry_run=True, strategies=["S2"])
        self.assertEqual(results[0].decision, "would_restart")
        self.assertEqual(results[0].action, "restart_skipped_dry_run")
        self.assertEqual(self.launch_calls, [])

    def test_execute_ok_strategy_does_not_restart(self) -> None:
        _write_hb(self.state_dir, "S2", _base_hb())
        results = self._run(dry_run=False, strategies=["S2"])
        self.assertEqual(results[0].decision, "ok")
        self.assertEqual(results[0].action, "none")
        self.assertEqual(self.launch_calls, [])

    def test_stale_dry_run_restart_skipped(self) -> None:
        self._write_offline_hb("S2", "binance_alpha_monitor", 400)
        results = self._run(dry_run=True, strategies=["S2"])
        self.assertEqual(results[0].action, "restart_skipped_dry_run")

    def test_stale_execute_attempts_one_restart(self) -> None:
        self._write_offline_hb("S2", "binance_alpha_monitor", 400)
        results = self._run(dry_run=False, strategies=["S2"])
        self.assertEqual(self.launch_calls, ["S2"])
        self.assertEqual(results[0].action, "restart_success")

    def test_cooldown_prevents_repeated_restart(self) -> None:
        self._write_offline_hb("S2", "binance_alpha_monitor", 400)
        history = RestartHistoryStore(self.history_path)
        history.append(
            {
                "id": "prev",
                "strategy": "S2",
                "reason": "test",
                "dryRun": False,
                "action": "restart_attempted",
                "oldPid": 1,
                "newPid": 2,
                "startedAt": _iso_now(self.now - timedelta(seconds=60)),
                "completedAt": _iso_now(self.now - timedelta(seconds=60)),
                "verifiedAt": None,
                "error": None,
            }
        )
        results = self._run(dry_run=False, strategies=["S2"], restart_cooldown_sec=900)
        self.assertEqual(results[0].action, "restart_skipped_cooldown")
        self.assertEqual(self.launch_calls, [])

    def test_max_restarts_per_hour_prevents_restart(self) -> None:
        self._write_offline_hb("S2", "binance_alpha_monitor", 400)
        history = RestartHistoryStore(self.history_path)
        for i in range(2):
            history.append(
                {
                    "id": f"e{i}",
                    "strategy": "S2",
                    "reason": "test",
                    "dryRun": False,
                    "action": "restart_attempted",
                    "oldPid": 1,
                    "newPid": 2,
                    "startedAt": _iso_now(self.now - timedelta(minutes=30 + i * 5)),
                    "completedAt": _iso_now(self.now - timedelta(minutes=30 + i * 5)),
                    "verifiedAt": None,
                    "error": None,
                }
            )
        results = self._run(
            dry_run=False,
            strategies=["S2"],
            max_restarts_per_hour=2,
            restart_cooldown_sec=60,
        )
        self.assertEqual(results[0].action, "restart_skipped_rate_limit")
        self.assertEqual(self.launch_calls, [])

    def test_multiple_would_restart_only_one(self) -> None:
        self._write_offline_hb("S2", "binance_alpha_monitor", 400)
        self._write_offline_hb("S4", "futures_alpha_scanner", 400)
        results = self._run_strategies(["S2", "S4"], dry_run=False)
        restarted = [r for r in results if r.action == "restart_success"]
        skipped = [r for r in results if r.action == "restart_skipped_multiple_candidates"]
        self.assertEqual(len(restarted), 1)
        self.assertEqual(restarted[0].strategy, "S2")
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0].strategy, "S4")
        self.assertEqual(self.launch_calls, ["S2"])

    def test_s5_business_sla_never_restarts(self) -> None:
        _write_hb(
            self.state_dir,
            "S5",
            _base_hb(
                strategy="S5",
                worker="heat_radar",
                status="sleeping",
                phase="sleep",
                lastHeartbeatAt=_iso_ago(30),
                nextRunAt=_iso_offset(1700),
                lastScanOutcome="binance_api_fail",
                lastScanCompletedAt=_iso_ago(4000),
                lastTelegramSentAt=_iso_ago(4000),
                consecutiveScanFailures=2,
                expectedIntervalSec=1800,
            ),
        )
        results = self._run(dry_run=False, strategies=["S5"])
        self.assertEqual(results[0].decision, "would_warn")
        self.assertEqual(results[0].action, "warn_only")
        self.assertEqual(self.launch_calls, [])

    def test_s3_sleeping_ok_never_restarts(self) -> None:
        _write_hb(
            self.state_dir,
            "S3",
            _base_hb(
                strategy="S3",
                worker="oi_funding_scanner",
                status="sleeping",
                phase="sleep",
                lastHeartbeatAt=_iso_ago(120),
                nextRunAt=_iso_offset(3600),
            ),
        )
        results = self._run(dry_run=False, strategies=["S3"])
        self.assertEqual(results[0].decision, "ok")
        self.assertEqual(results[0].action, "none")
        self.assertEqual(self.launch_calls, [])

    def test_invalid_restart_history_backed_up(self) -> None:
        self.history_path.write_text("{bad json", encoding="utf-8")
        store = RestartHistoryStore(self.history_path)
        self.assertEqual(store.events, [])
        backups = list(self.state_dir.glob("watchdog-restart-history.corrupt-*.json"))
        self.assertEqual(len(backups), 1)

    def test_post_restart_verification_success(self) -> None:
        started = self.now - timedelta(seconds=5)
        _write_hb(
            self.state_dir,
            "S2",
            _base_hb(
                strategy="S2",
                worker="binance_alpha_monitor",
                pid=999,
                lastHeartbeatAt=_iso_now(self.now),
            ),
        )
        ok, verified_at, err = verify_post_restart(
            "S2",
            state_dir=self.state_dir,
            restart_started_at=started,
            timeout_sec=2,
            interval_sec=0,
            is_process_alive_fn=lambda pid: True if pid == 999 else False,
            sleep_fn=lambda _s: None,
        )
        self.assertTrue(ok)
        self.assertIsNotNone(verified_at)
        self.assertIsNone(err)

    def test_post_restart_verification_timeout(self) -> None:
        started = self.now
        _write_hb(
            self.state_dir,
            "S2",
            _base_hb(
                strategy="S2",
                worker="binance_alpha_monitor",
                pid=999,
                lastHeartbeatAt=_iso_ago(120),
            ),
        )
        ok, verified_at, err = verify_post_restart(
            "S2",
            state_dir=self.state_dir,
            restart_started_at=started,
            timeout_sec=0,
            interval_sec=0,
            is_process_alive_fn=lambda pid: True if pid == 999 else False,
            sleep_fn=lambda _s: None,
        )
        self.assertFalse(ok)
        self.assertIsNone(verified_at)
        self.assertEqual(err, "verification_timeout")

    def test_unsafe_pid_skips_restart(self) -> None:
        self._write_offline_hb("S2", "binance_alpha_monitor", 400)
        (self.pid_dir / "S2.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
        results = self._run(
            dry_run=False,
            strategies=["S2"],
            verify_pid_fn=lambda _s, _p: False,
        )
        self.assertEqual(results[0].action, "restart_skipped_unsafe_pid_match")
        self.assertEqual(self.launch_calls, [])


def _iso_now(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


if __name__ == "__main__":
    unittest.main()
