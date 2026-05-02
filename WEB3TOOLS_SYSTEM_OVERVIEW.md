# Web3Tools 系统总览与大纲

本文档汇总 **AI Quant / Web3 监控与策略** 相关目录、与桌面 Roadmap 的对照关系，以及各模块职责。各子目录的**具体改动与迭代**见对应仓库（模块）根目录下的 `CHANGELOG.md`。

---

## 1. 项目目标（摘自 Roadmap）

构建完整的：**链上扫描 + 合约信号 + AI 辅助 + 调度执行** 的量化体系。Python 负责计算与扫描，Node 作中间层，WebUI 作控制台；自动交易放在最后阶段，且 **AI 不直接下单**。

---

## 2. 目标架构（Roadmap）

```
Python（策略计算） → Node（中间层） → WebUI（控制台） → Hermes（调度） → GPT（学习） → 执行系统
```

当前仓库内已落地的部分覆盖 **Python 策略层**、**Node ingestion/API（web3-monitor-backed）** 与 **Web 前端（web3-monitor）**；其中数据库主存储已确定迁移为 PostgreSQL（单库方案）。

---

## 3. Roadmap 阶段对照

| 阶段 | 内容 | 与 Web3Tools 现状 |
|------|------|-------------------|
| Phase 1 | 策略可运行；统一 JSON 输出 | 已完成：策略可独立运行，且统一 JSON 输出已接入 `Core-Strategy/node_bridge.py` |
| Phase 2 | 定义 signal schema；Python → JSON | 已完成基础信封与事件结构：支持 envelope 与 compact event 两种上报体 |
| Phase 3 | Node 接收策略数据；入库 + API | 已完成第一版：`POST /api/core-strategy/ingest`、`GET /api/core-strategy/recent` |
| Phase 4 | WebUI：策略控制台、Worker、信号、TG 配置 | `web3-monitor` 前端演进中 |
| Phase 5 | 本地跑通 Python → Node → DB → UI → TG | 部分已跑通（Python → Node → DB 已联通）；UI 改造与 TG 由 Node 统一转发仍在推进 |
| Phase 6–9 | GPT/Hermes、回测、部署、自动交易 | 规划中 |

**Roadmap 原文路径（本机）：** `c:\Users\ASUS\Desktop\ai_quant_roadmap.md`  
（若移动位置，请在本节自行更新路径说明。）

---

## 4. Web3Tools 目录与模块职责

```
Web3Tools/
├── WEB3TOOLS_SYSTEM_OVERVIEW.md    # 本总览
├── Core-Strategy/                  # Python 策略集合（核心计算层）
│   ├── env_loader.py               # 共享：从 accumulation-radar/.env.oi 加载 TG 等
│   ├── CHANGELOG.md                # 跨模块基础设施变更记录
│   ├── accumulation-radar/         # 庄家收筹 + OI/费率/三策略雷达
│   ├── accumulation-fastsignal-radar/  # 热度 + CG + 放量 + OI
│   ├── onChain-radar/              # 链上叙事 / GMGN / 动量推送
│   ├── binance-alpha-monitor/      # 币安 Alpha 公告监控 + 评级 + TG
│   └── Ai-Trading/                 # 合约扫描、虚拟仓位与 TG（非实盘下单）
├── web3-monitor-backed/          # Fastify + Prisma 后端（ingest / query / 存储层）
└── web3-monitor/                 # Next.js 前端（策略控制台与展示；调用 Node API）
```

### 4.1 共享配置

- **Telegram**：统一从 `Core-Strategy/accumulation-radar/.env.oi` 读取 `TG_BOT_TOKEN`、`TG_CHAT_ID`（通过 `env_loader.load_shared_env`）。
- **安全**：Token 勿提交到 Git；泄露后应在 BotFather 轮换。

### 4.2 策略模块一览

| 模块 | 入口脚本（s1–s5 编号） | 主要数据源 | 输出形态（当前） |
|------|-----------|------------|------------------|
| onChain-radar | `s1_on_chain_narrative_radar.py` | GMGN、DEXScreener 等 | TG；SQLite 叙事库 |
| binance-alpha-monitor | `s2_alpha_monitor.py` | 币安公告 API、CoinGecko；可选 LLM | TG HTML；SQLite |
| Ai-Trading | `s3_futures_alpha_autonomous_trading_v1.py` | 币安合约 + FGI 等 | `trades.json` + TG |
| accumulation-radar | `s4_accumulation_radar.py` | 币安合约 REST | TG Markdown；本地 SQLite |
| accumulation-fastsignal-radar | `s5_accumulation_radar.py` | 币安 + CoinGecko + 广场热度（尽力） | TG Markdown |

### 4.3 建议运行方式（摘要）

- 设置 `PYTHONUNBUFFERED=1`（Windows 下便于实时日志）。
- 收筹雷达：`pool` 与 `oi` 建议分步执行；无参数时为常驻调度循环。
- 链上雷达：可用 `python s1_on_chain_narrative_radar.py once` 做单次扫描。
- 详见各模块 `CHANGELOG.md` 与脚本内注释。

---

## 5. 与各 CHANGELOG 的对应关系

| 文档 | 路径 |
|------|------|
| 共享基础设施 | `Core-Strategy/CHANGELOG.md` |
| 庄家收筹雷达 | `Core-Strategy/accumulation-radar/CHANGELOG.md` |
| 热度做多雷达 | `Core-Strategy/accumulation-fastsignal-radar/CHANGELOG.md` |
| 链上叙事雷达 | `Core-Strategy/onChain-radar/CHANGELOG.md` |
| Alpha 监控 | `Core-Strategy/binance-alpha-monitor/CHANGELOG.md` |
| 合约扫描 / 虚拟交易 | `Core-Strategy/Ai-Trading/CHANGELOG.md` |

---

## 6. 后续工作（对齐 Roadmap「当前下一步」）

1. 完成 **web3-monitor-backed** 从 MySQL/MariaDB 到 **PostgreSQL 单库**迁移（Prisma provider / migration / env 全面切换）。
2. `GET /api/core-strategy/recent` 增强筛选（worker、strategy、symbol、side、status）与 `GET /api/core-strategy/workers`。
3. WebUI：总览/交易所/链上页面替换 mock 信号为后端真实策略数据，补齐 worker 状态区与详情弹窗 payload 展示。
4. Node 侧统一 TG 推送通道（Python 保持只负责计算与 HTTP 上报）。

---

*文档生成说明：结构与 Roadmap 对齐；技术细节以代码与各目录 `CHANGELOG.md` 为准。*
