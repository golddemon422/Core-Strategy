# Core-Strategy 共享层变更记录

本文件记录 **跨多个策略模块** 的基础设施改动。各策略独有逻辑见各自目录下的 `CHANGELOG.md`。

---

## 2026-05-01

### 新增 `env_loader.py`（共享环境加载）

- **目的**：所有策略统一从 `accumulation-radar/.env.oi` 读取 `TG_BOT_TOKEN`、`TG_CHAT_ID`，避免各子目录重复维护多份密钥文件。
- **行为**：
  - `load_shared_env(__file__)`：按「策略脚本所在目录的上级的上级 = Core-Strategy 根」定位 `accumulation-radar/.env.oi`，使用 `os.environ.setdefault` 写入（**已存在的系统环境变量优先生效**）。
  - 若已配置 `TG_BOT_TOKEN`，自动 `setdefault` `TELEGRAM_BOT_TOKEN`，兼容旧变量名。
- **`ensure_utf8_stdio()`**：在 Windows 下将 `stdout`/`stderr` 设为 UTF-8（`errors="replace"`），减少策略脚本打印 emoji 时的 `UnicodeEncodeError`（GBK 控制台）。

### 影响范围

- 被以下模块引用：`accumulation-radar`、`accumulation-fastsignal-radar`、`onChain-radar`、`binance-alpha-monitor`、`Ai-Trading`（均通过 `sys.path` 插入 Core-Strategy 根目录后 `from env_loader import load_shared_env`）。

### 运维提示

- `.env.oi` 仅保存在本地，勿提交版本库；Token 泄露需在 BotFather 轮换。

---

*按时间倒序追加新条目；重大行为变更请标注「破坏性变更」。*
