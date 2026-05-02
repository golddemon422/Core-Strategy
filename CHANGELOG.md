# Core-Strategy 共享层变更记录

本文件记录 **跨多个策略模块** 的基础设施改动。各策略独有逻辑见各自目录下的 `CHANGELOG.md`。

---

## 2026-05-02 — node_bridge 资金费率字段

### `canonical_exchange_metrics` / `fr_pct`

- **`fr_pct` 写入 `metrics.fundingRateSignal`**，不再写入 `fundingRate`，与后端归一化及 WebUI「策略费率信号」一致。
- 实盘 **资金费率** 由前端经后端 **`/api/exchange/binance-funding`** 拉取币安 `premiumIndex`。

### accumulation-radar（S4）补充（摘要）

- **OI 异动 / 空头燃料 / 收筹池** 等与 Telegram 同源的 **逐标的** `POST` Node 事件（`subType`、`scan_batch_id`、`event_scope=symbol`），便于交易所工作台按 tab 计数与筛选。细节见策略脚本与仓库根 `WEB3TOOLS_SYSTEM_OVERVIEW.md`。

---

## 2026-05-01 — 与 Web3 Monitor / 后端对齐

### Ingest `worker` 约定（链上叙事）

- 上报 JSON 中建议使用 **`worker: "onchain-radar"`**，与前端 `web3-monitor` 注册表一致，链上页按后端 **`type=onchain`** 展示。
- 历史别名 **`onchain_narrative_radar`** 在前端仍映射为同一 worker 展示名。

### 新增 `env_loader.py`（共享环境加载）

- **目的**：所有策略统一从 `accumulation-radar/.env.oi` 读取 `TG_BOT_TOKEN`、`TG_CHAT_ID`，避免各子目录重复维护多份密钥文件。
- **行为**：
  - `load_shared_env(__file__)`：按「策略脚本所在目录的上级的上级 = Core-Strategy 根」定位 `accumulation-radar/.env.oi`，使用 `os.environ.setdefault` 写入（**已存在的系统环境变量优先生效**）。
  - 若已配置 `TG_BOT_TOKEN`，自动 `setdefault` `TELEGRAM_BOT_TOKEN`，兼容旧变量名。
- **`ensure_utf8_stdio()`**：在 Windows 下将 `stdout`/`stderr` 设为 UTF-8（`errors="replace"`），减少策略脚本打印 emoji 时的 `UnicodeEncodeError`（GBK 控制台）。

### 影响范围

- 被以下模块引用：`accumulation-radar`、`accumulation-fastsignal-radar`、`onChain-radar`、`binance-alpha-monitor`、`Ai-Trading`（均通过 `sys.path` 插入 Core-Strategy 根目录后 `from env_loader import load_shared_env`）。

### 新增 `node_bridge.py`（统一策略输出桥）

- **目的**：统一策略输出格式，供 Node 后端消费；保持 Python 仅做计算层，不直连数据库。
- **输出能力**：
  - 文件输出：`node_out/{strategy_id}_latest.json`
  - 事件流追加：`node_out/signals.jsonl`、`node_out/events.jsonl`
  - HTTP 上报：当设置 `CORE_STRATEGY_INGEST_URL` 时，自动 POST 到 Node 的 ingest API。
- **鉴权头**：
  - 优先读取 `STRATEGY_INGEST_SECRET`
  - 兼容 `STRATEGY_INGEST_TOKEN` 旧变量名
  - 请求头统一为 `x-strategy-token`
- **当前接口约定**：默认拼接 `.../api/core-strategy/ingest`，也兼容直接传入以 `/ingest` 结尾的完整 URL。

### 运维提示

- `.env.oi` 仅保存在本地，勿提交版本库；Token 泄露需在 BotFather 轮换。
- Python 侧 HTTP 上报依赖 `requests`；若缺失请安装后再启用 ingest。

---

*按时间倒序追加新条目；重大行为变更请标注「破坏性变更」。*
