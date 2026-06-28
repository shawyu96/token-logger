"""
token-logger — 记录每次 LLM API 调用的真实 token 消耗（输入/输出/缓存）。

不估算费用，只记录 DeepSeek API 返回的原始 token 数。
数据写到本地 SQLite，不受 Hermes 更新的影响。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_DB_LOCK = threading.Lock()


def _db_path() -> str:
    return os.path.join(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")), "token-usage.db")


def _init_db():
    with _DB_LOCK:
        db = sqlite3.connect(_db_path())
        db.execute("""
            CREATE TABLE IF NOT EXISTS api_calls (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     REAL NOT NULL,
                session_id    TEXT NOT NULL,
                turn_id       TEXT DEFAULT '',
                api_req_id    TEXT DEFAULT '',
                model         TEXT NOT NULL,
                provider      TEXT DEFAULT '',
                input_tokens  INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read    INTEGER DEFAULT 0,
                cache_write   INTEGER DEFAULT 0,
                reasoning     INTEGER DEFAULT 0,
                duration_ms   REAL DEFAULT 0.0,
                finish_reason TEXT DEFAULT '',
                raw_usage     TEXT DEFAULT ''
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_calls_session
            ON api_calls(session_id, timestamp)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_calls_time
            ON api_calls(timestamp)
        """)
        db.commit()
        db.close()


# ── Hook 函数 ──────────────────────────────────────────────

def on_post_api_request(*,
                        task_id: str = "",
                        session_id: str = "",
                        provider: str = "",
                        base_url: str = "",
                        model: str = "",
                        api_call_count: int = 0,
                        usage: Any = None,
                        api_duration: float = 0.0,
                        finish_reason: str = "",
                        turn_id: str = "",
                        api_request_id: str = "",
                        **_: Any) -> None:
    """post_api_request hook — 每次 API 调用完成后触发，记录真实 token 数据"""
    if not usage or not isinstance(usage, dict):
        return

    inp = usage.get("input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0) or 0
    cache_read = usage.get("cache_read_tokens", 0) or 0
    cache_write = usage.get("cache_write_tokens", 0) or 0
    reasoning = usage.get("reasoning_tokens", 0) or 0

    try:
        with _DB_LOCK:
            db = sqlite3.connect(_db_path())
            db.execute(
                """INSERT INTO api_calls
                   (timestamp, session_id, turn_id, api_req_id, model, provider,
                    input_tokens, output_tokens, cache_read, cache_write, reasoning,
                    duration_ms, finish_reason, raw_usage)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    time.time(),
                    session_id,
                    turn_id or "",
                    api_request_id or "",
                    model,
                    provider,
                    inp,
                    out,
                    cache_read,
                    cache_write,
                    reasoning,
                    round(api_duration * 1000, 2),
                    finish_reason or "",
                    json.dumps(usage, ensure_ascii=False),
                ),
            )
            db.commit()
            db.close()
    except Exception as e:
        logger.error(f"token-logger: 写入失败: {e}")


# ── 注册入口 ───────────────────────────────────────────────

def register(ctx) -> None:
    _init_db()
    ctx.register_hook("post_api_request", on_post_api_request)
    logger.info("token-logger: 已注册 post_api_request hook")
