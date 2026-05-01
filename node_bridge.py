"""统一 JSON 输出，供 Node 后端读取（文件接口）。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1"
OUT_DIR = Path(__file__).resolve().parent / "node_out"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_strategy_output(
    strategy_id: str,
    mode: str,
    payload: dict[str, Any],
    *,
    append_jsonl: bool = True,
) -> Path:
    """
    写入 node_out/{strategy_id}_latest.json，并可选用 signals.jsonl 追加一行。
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "mode": mode,
        "generated_at": _utc_iso(),
        "payload": payload,
    }
    text = json.dumps(envelope, ensure_ascii=False, indent=2, default=str)
    latest = OUT_DIR / f"{strategy_id}_latest.json"
    latest.write_text(text, encoding="utf-8")
    if append_jsonl:
        with open(OUT_DIR / "signals.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(envelope, ensure_ascii=False, default=str) + "\n")
    return latest


def append_signal_event(strategy_id: str, event: dict[str, Any]) -> None:
    """单行事件流（触发/回调等），便于 Node tail。"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    line = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "generated_at": _utc_iso(),
        **event,
    }
    with open(OUT_DIR / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
