"""Load shared Telegram credentials from accumulation-radar/.env.oi (Core-Strategy root)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def ensure_utf8_stdio() -> None:
    """Avoid UnicodeEncodeError on Windows consoles when printing emoji."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

_SHARED_ENV_DIR = "accumulation-radar"
_SHARED_ENV_NAME = ".env.oi"


def core_strategy_root(script_file: str) -> Path:
    """Core-Strategy folder: parent of the strategy package directory."""
    return Path(script_file).resolve().parent.parent


def shared_env_path(script_file: str) -> Path:
    return core_strategy_root(script_file) / _SHARED_ENV_DIR / _SHARED_ENV_NAME


def load_shared_env(script_file: str) -> Path | None:
    """
    Set TG_BOT_TOKEN, TG_CHAT_ID (and TELEGRAM_BOT_TOKEN alias) from shared .env.oi.
    Uses setdefault so existing OS env wins.
    Returns path if file exists, else None.
    """
    ensure_utf8_stdio()
    path = shared_env_path(script_file)
    if not path.is_file():
        return None
    # Telegram 路由以共享文件为准，避免系统/用户环境变量里残留旧 TG_CHAT_ID
    _TG_FROM_FILE = {"TG_BOT_TOKEN", "TG_CHAT_ID"}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                key, val = k.strip(), v.strip()
                if key in _TG_FROM_FILE:
                    os.environ[key] = val
                else:
                    os.environ.setdefault(key, val)
    tok = os.environ.get("TG_BOT_TOKEN", "")
    if tok:
        os.environ["TELEGRAM_BOT_TOKEN"] = tok
    return path
