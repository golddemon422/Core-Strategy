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
    evaluate_strategy,
    compute_exit_code,
    read_heartbeat_file,
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


if __name__ == "__main__":
    unittest.main()
