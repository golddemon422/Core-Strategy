"""统一 JSON 输出，供 Node 后端读取（文件接口 + 可选 HTTP 上报）。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1"
OUT_DIR = Path(__file__).resolve().parent / "node_out"
_INGEST_WARNED_NO_URL = False
_INGEST_WARNED_NO_SECRET = False


def _post_to_monitor_backed(envelope: dict[str, Any]) -> None:
    """若设置 CORE_STRATEGY_INGEST_URL，则 POST 到 web3-monitor-backed。"""
    global _INGEST_WARNED_NO_URL, _INGEST_WARNED_NO_SECRET
    url = (os.environ.get("CORE_STRATEGY_INGEST_URL") or "").strip().rstrip("/")
    if not url:
        if not _INGEST_WARNED_NO_URL:
            _INGEST_WARNED_NO_URL = True
            print(
                "[node_bridge] CORE_STRATEGY_INGEST_URL 未设置，已跳过 HTTP 入库；"
                "WebUI Worker 心跳依赖入库时间，请在 accumulation-radar/.env.oi 配置 URL 与 STRATEGY_INGEST_SECRET。"
            )
        return
    ingest_url = url if url.endswith("/ingest") else f"{url}/api/core-strategy/ingest"
    token = (
        os.environ.get("STRATEGY_INGEST_SECRET") or os.environ.get("STRATEGY_INGEST_TOKEN") or ""
    ).strip()
    if not token:
        if not _INGEST_WARNED_NO_SECRET:
            _INGEST_WARNED_NO_SECRET = True
            print(
                "[node_bridge] STRATEGY_INGEST_SECRET 未设置，ingest 将 401；"
                "请与 web3-monitor-backed 的 STRATEGY_INGEST_SECRET 一致写入 .env.oi。"
            )
        return
    try:
        import requests

        headers = {"Content-Type": "application/json", "x-strategy-token": token}
        r = requests.post(ingest_url, json=envelope, headers=headers, timeout=15)
        if r.status_code not in (200, 201):
            print(f"[node_bridge] ingest HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[node_bridge] ingest failed: {e}")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


PRIORITY_RANK_CN = {"高": 3, "中": 2, "观察": 1}


def canonical_exchange_metrics(
    metrics: dict[str, Any] | None = None,
    *,
    oi_usd: float | None = None,
    fr_pct: float | None = None,
    px_chg: float | None = None,
    d6h: float | None = None,
    vol: float | None = None,
    est_mcap: float | None = None,
    sw_days: float | None = None,
    range_pct: float | None = None,
    avg_vol: float | None = None,
    heat: float | None = None,
    price: float | None = None,
    trend_label: str | None = None,
    pool_sc: float | None = None,
) -> dict[str, Any]:
    """
    与 Node normalize-exchange-signal 对齐的 metrics 键名。
    别名：oi_usd→openInterest, fr_pct→fundingRate, px_chg→priceChange24h, d6h→oiChange, vol→volume24h/volume
    """
    m: dict[str, Any] = dict(metrics) if metrics else {}
    if oi_usd is not None:
        m.setdefault("openInterest", oi_usd)
    if fr_pct is not None:
        m.setdefault("fundingRateSignal", fr_pct)
    if px_chg is not None:
        m.setdefault("priceChange24h", px_chg)
        m.setdefault("priceChange", px_chg)
    if d6h is not None:
        m.setdefault("oiChange", d6h)
    if vol is not None:
        m.setdefault("volume24h", vol)
        m.setdefault("volume", vol)
    if est_mcap is not None:
        m.setdefault("marketCap", est_mcap)
    if sw_days is not None:
        m.setdefault("rangeDays", sw_days)
    if range_pct is not None:
        m.setdefault("volatility", range_pct)
    if avg_vol is not None:
        m.setdefault("avgVolume", avg_vol)
    if heat is not None:
        m.setdefault("heatScore", heat)
    if price is not None:
        m.setdefault("price", price)
    if trend_label:
        m.setdefault("trendLabel", trend_label)
    if pool_sc is not None:
        m.setdefault("poolScore", pool_sc)
    return m


def compute_exchange_priority_cn(
    *,
    strategy_group: str,
    sub_type: str,
    score: float | None,
    oi_change: float | None,
    funding_rate: float | None,
    price_change: float | None,
    heat_score: float | None,
    reasons: list[str] | None,
) -> tuple[str, int]:
    """
    与 Node/Web 约定一致：高 / 中 / 观察
    """
    st = (sub_type or "").strip()
    rs = reasons or []
    blob = " ".join(rs)

    if strategy_group == "S4":
        if st in ("回调买点", "变化触发", "空头燃料", "OI异动", "oi异动"):
            return "高", PRIORITY_RANK_CN["高"]
        if score is not None and score >= 80:
            return "高", PRIORITY_RANK_CN["高"]
        if oi_change is not None and abs(float(oi_change)) >= 30:
            return "高", PRIORITY_RANK_CN["高"]
        if funding_rate is not None and abs(float(funding_rate)) >= 1.0:
            return "高", PRIORITY_RANK_CN["高"]
        if any(k in blob for k in ("重点关注", "值得关注", "最高优先级")):
            return "高", PRIORITY_RANK_CN["高"]
        if st in ("收筹池", "三策略"):
            return "观察", PRIORITY_RANK_CN["观察"]
        return "中", PRIORITY_RANK_CN["中"]

    if strategy_group == "S5":
        if st in ("Squeeze", "squeeze", "追多燃料") or "squeeze" in st.lower():
            return "高", PRIORITY_RANK_CN["高"]
        if heat_score is not None and float(heat_score) >= 75:
            return "高", PRIORITY_RANK_CN["高"]
        if price_change is not None and float(price_change) >= 20:
            return "高", PRIORITY_RANK_CN["高"]
        if oi_change is not None and abs(float(oi_change)) >= 20:
            return "高", PRIORITY_RANK_CN["高"]
        if any(k in blob for k in ("值得关注", "高热度", "追多")):
            return "高", PRIORITY_RANK_CN["高"]
        if st in ("热度榜",):
            return "中", PRIORITY_RANK_CN["中"]
        if st in ("值得关注",):
            return "观察", PRIORITY_RANK_CN["观察"]
        return "中", PRIORITY_RANK_CN["中"]

    return "中", PRIORITY_RANK_CN["中"]


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
        "event_scope": "batch",
        "payload": payload,
    }
    text = json.dumps(envelope, ensure_ascii=False, indent=2, default=str)
    latest = OUT_DIR / f"{strategy_id}_latest.json"
    latest.write_text(text, encoding="utf-8")
    if append_jsonl:
        with open(OUT_DIR / "signals.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(envelope, ensure_ascii=False, default=str) + "\n")
    _post_to_monitor_backed(envelope)
    return latest


def build_exchange_event(
    *,
    strategy_id: str,
    strategy_group: str,
    sub_type: str,
    symbol: str,
    raw_text: str,
    metrics: dict[str, Any] | None = None,
    reasons: list[str] | None = None,
    risk_notes: list[str] | None = None,
    side: str = "watch",
    status: str = "watch",
    score: float | None = None,
    confidence: float | None = None,
    priority: str | None = None,
    priority_rank: int | None = None,
    worker: str | None = None,
    strategy: str | None = None,
    scan_batch_id: str | None = None,
) -> dict[str, Any]:
    """
    推荐上报形态：与 Telegram 推送同文的 rawText 一并写入 event，供 Node 与 WebUI 对齐。
    strategy_group: \"S4\" | \"S5\"
    """
    event_body: dict[str, Any] = {
        "type": "exchange",
        "worker": worker or strategy_id,
        "strategy": strategy or strategy_id,
        "strategyGroup": strategy_group,
        "subType": sub_type,
        "eventScope": "symbol",
        "symbol": symbol,
        "side": side,
        "status": status,
        "rawText": raw_text,
        "rawTelegramText": raw_text,
        "metrics": metrics or {},
        "reasons": reasons or [],
        "riskNotes": risk_notes or [],
    }
    if score is not None:
        event_body["score"] = score
    if confidence is not None:
        event_body["confidence"] = confidence
    if priority:
        event_body["priority"] = priority
    if priority_rank is not None:
        event_body["priorityRank"] = priority_rank
    if scan_batch_id:
        event_body["scanBatchId"] = scan_batch_id
    envelope: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "generated_at": _utc_iso(),
        "event_scope": "symbol",
        "event": event_body,
    }
    if scan_batch_id:
        envelope["scan_batch_id"] = scan_batch_id
    return envelope


def post_exchange_event_to_node(**kwargs: Any) -> None:
    """构建含 rawText 的 exchange 信封并 POST 至 CORE_STRATEGY_INGEST_URL（与 write_strategy_output 同源）。"""
    _post_to_monitor_backed(build_exchange_event(**kwargs))


def append_signal_event(strategy_id: str, event: dict[str, Any]) -> None:
    """单行事件流（触发/回调等），便于 Node tail。"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    line = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "generated_at": _utc_iso(),
        "event_scope": "symbol",
        **event,
    }
    with open(OUT_DIR / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
    _post_to_monitor_backed(line)
