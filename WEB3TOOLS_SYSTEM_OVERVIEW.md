# Web3Tools 系统总览与大纲

> 与仓库根目录 `Web3Tools/WEB3TOOLS_SYSTEM_OVERVIEW.md` **内容同步**；在仅克隆 `Core-Strategy` 时可单独阅读本文件。

本文档汇总 **AI Quant / Web3 监控与策略** 相关目录、与桌面 Roadmap 的对照关系，以及各模块职责。各子目录的**具体改动与迭代**见对应 `CHANGELOG.md`。

---

## 1. 项目目标（摘自 Roadmap）

构建完整的：**链上扫描 + 合约信号 + AI 辅助 + 调度执行** 的量化体系。Python 负责计算与扫描，Node 作中间层，WebUI 作控制台；自动交易放在最后阶段，且 **AI 不直接下单**。

---

## 2. 目标架构（Roadmap）

```
Python（策略计算） → Node（中间层） → WebUI（控制台） → Hermes（调度） → GPT（学习） → 执行系统
```

当前仓库内已落地的部分覆盖 **Python 策略层**、**Node ingestion/API（web3-monitor-backed）** 与 **Web 前端（web3-monitor）**；数据库主存储为 **PostgreSQL**（Prisma 单库方案）。

---

## 3. Roadmap 阶段对照

| 阶段 | 内容 | 与 Web3Tools 现状 |
|------|------|-------------------|
| Phase 1 | 策略可运行；统一 JSON 输出 | 已完成：`node_bridge.py` 统一信封与 HTTP 上报 |
| Phase 2 | 定义 signal schema；Python → JSON | 已完成：envelope 与 compact event |
| Phase 3 | Node 接收；入库 + API | 已完成：`/api/core-strategy/ingest`、`/recent`、`/workers` |
| Phase 4 | WebUI 控制台 | 交易所 / 链上工作台、Worker 心跳、S4/S5 雷达 |
| Phase 5 | Python → Node → DB → UI | 已跑通 |
| Phase 6–9 | GPT/Hermes、自动交易 | 规划中 |

**Roadmap 原文路径（本机）：** `c:\Users\ASUS\Desktop\ai_quant_roadmap.md`

---

## 4. 目录与模块职责

```
Core-Strategy/
├── env_loader.py          # 共享 .env.oi
├── node_bridge.py         # HTTP ingest；canonical metrics；fr_pct → fundingRateSignal
├── CHANGELOG.md
├── accumulation-radar/    # S4：收筹池、OI异动、空头燃料等 **逐标的 ingest**
├── accumulation-fastsignal-radar/
├── onChain-radar/
├── binance-alpha-monitor/
└── Ai-Trading/
```

### 4.1 共享配置

- Telegram：`accumulation-radar/.env.oi`
- Ingest：`CORE_STRATEGY_INGEST_URL`、`STRATEGY_INGEST_SECRET` / `STRATEGY_INGEST_TOKEN`

### 4.2 策略模块一览

| 模块 | 入口 | 数据源 | 输出 |
|------|------|--------|------|
| accumulation-radar | `s4_accumulation_radar.py` | 币安合约 REST | Node 逐标的 + TG + SQLite |
| accumulation-fastsignal-radar | `s5_accumulation_radar.py` | 币安 + CG 等 | TG + ingest |
| 其他 | s1–s3 | 见根总览 | — |

### 4.3 `node_bridge` 与资金费率字段

- **`fundingRateSignal`**：由 `canonical_exchange_metrics(..., fr_pct=...)` 等写入，表示策略侧费率/信号，**不等于** 币安 `lastFundingRate`。
- 实盘 **资金费率** 由 **web3-monitor** 经 **`/api/exchange/binance-funding`（premiumIndex）** 展示；**策略费率信号** 用 `fundingRateSignal` / TG「费率」解析，**勿**将前者标为后者。

### 4.4 合约工作台与 S5 运行（与 `web3-monitor` 对齐摘要）

- **Node `recent` 拉取**：工作台建议 **`type=exchange`、`eventScope=all`、`limit≤600`**，以同时包含 **逐标的** 与 **`write_strategy_output` 的 `batch`** 行；仅 `symbol` 时 batch 不进入列表。
- **Worker 状态 `x/3`**：只计 **S4** `accumulation_radar`、**S5** `heat_radar`、**S3** `futures_alpha_scanner`；**Worker 心跳** 条带白名单同三（不含 `binance_alpha_monitor`）。心跳绿/红由 **全表** 该 worker 最后 `createdAt` 与约 **12h** 阈值决定。
- **S5**：`s5_accumulation_radar.py` **无参** = 常驻、**每 30 分钟**一轮；**`once`** = 单轮。末轮 **`write_strategy_output`** 为 **batch**；热币循环 **`append_signal_event`** 为 **symbol** 级。

---

## 5. CHANGELOG 索引

| 文档 | 路径 |
|------|------|
| 共享层 | `Core-Strategy/CHANGELOG.md` |
| 根总览 | `../WEB3TOOLS_SYSTEM_OVERVIEW.md`（与本文 **内容同步**，详述以根文档为准） |

---

## 6. 后续工作

见根目录 `WEB3TOOLS_SYSTEM_OVERVIEW.md` 第 6 节。

---

*技术细节以代码与 `CHANGELOG.md` 为准。*
