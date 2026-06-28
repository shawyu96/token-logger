#!/usr/bin/env python3
"""token-usage — 查询 token 消耗明细（独立脚本，不依赖插件）

从 token-usage.db 直接读取数据，插件只需要写数据到这里。

用法:
  tusage daily                  # 每日汇总
  tusage session                # 按对话汇总
  tusage list                   # 列出会话
  tusage turn <session_id>      # 看单次对话明细
  tusage daily 30               # 最近30天
"""
import sys, os, sqlite3, time

USAGE_DB  = os.path.expanduser("~/.hermes/token-usage.db")
HERMES_DB = os.path.expanduser("~/.hermes/state.db")

_TZ_HOURS = int(time.localtime().tm_gmtoff // 3600)
_TZ_OFFSET = f"{'+' if _TZ_HOURS >= 0 else ''}{_TZ_HOURS} hours"

if not os.path.exists(USAGE_DB):
    print("（暂无数据，新会话跑几轮后即可看到）")
    sys.exit(0)


def title_of(sid: str) -> str:
    try:
        con = sqlite3.connect(HERMES_DB)
        r = con.execute("SELECT title FROM sessions WHERE id=?", (sid,)).fetchone()
        return (r[0] or "")[:28] if r else ""
    except:
        return ""
    finally:
        try: con.close()
        except: pass


def _parse_days(s: str) -> int:
    try: return int(s) if s else 7
    except: return 7


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "daily"
    arg2 = sys.argv[2] if len(sys.argv) > 2 else ""
    db = sqlite3.connect(USAGE_DB)
    db.row_factory = sqlite3.Row

    if cmd == "daily":
        days = _parse_days(arg2)
        since = time.time() - days * 86400
        rows = db.execute(f"""
            SELECT date(datetime(timestamp,'unixepoch','{_TZ_OFFSET}')) as day,
                   count(*) calls, sum(input_tokens) ti, sum(output_tokens) tok_out, sum(cache_read) tc
FROM api_calls WHERE timestamp>=? GROUP BY day ORDER BY day DESC
        """, (since,)).fetchall()
        if not rows: return print("（暂无数据）")
        print(f"{'日期':<10} {'次数':>4} {'输入':>10} {'输出':>10} {'缓存':>12}")
        print("-" * 50)
        si, so, sc, sn = 0,0,0,0
        for r in rows:
            print(f"{r['day']:<10} {r['calls']:>4} {r['ti']:>10,} {r['tok_out']:>10,} {r['tc']:>12,}")
            sn+=r['calls']; si+=r['ti']; so+=r['tok_out']; sc+=r['tc']
        print("-" * 50)
        print(f"{'∑':<10} {sn:>4} {si:>10,} {so:>10,} {sc:>12,}")

    elif cmd == "session":
        days = _parse_days(arg2)
        since = time.time() - days * 86400
        rows = db.execute("""
            SELECT session_id sid, min(model) model, count(*) calls,
                   sum(input_tokens) ti, sum(output_tokens) tok_out, sum(cache_read) tc
            FROM api_calls WHERE timestamp>=?
            GROUP BY sid ORDER BY max(timestamp) DESC
        """, (since,)).fetchall()
        if not rows: return print("（暂无数据）")
        print(f"{'对话':<28} {'模型':<16} {'次':>3} {'输入':>9} {'输出':>9} {'缓存':>10}")
        print("-" * 79)
        for r in rows:
            t = title_of(r['sid']) or r['sid'][-14:]
            print(f"{t:<28} {r['model']:<16} {r['calls']:>3} {r['ti']:>9,} {r['tok_out']:>9,} {r['tc']:>10,}")

    elif cmd == "list":
        days = _parse_days(arg2)
        since = time.time() - days * 86400
        rows = db.execute("""
            SELECT session_id sid, count(*) calls,
                   sum(input_tokens) ti, sum(output_tokens) tok_out, sum(cache_read) tc
            FROM api_calls WHERE timestamp>=?
            GROUP BY sid ORDER BY max(timestamp) DESC
        """, (since,)).fetchall()
        if not rows: return print("（暂无数据）")
        print(f"{'ID(尾14位)':<18} {'对话':<28} {'次':>3} {'输入':>9} {'输出':>9} {'缓存':>10}")
        print("-" * 81)
        for r in rows:
            sid = r['sid'][-14:]
            t = title_of(r['sid']) or '（无标题）'
            print(f"{sid:<18} {t:<28} {r['calls']:>3} {r['ti']:>9,} {r['tok_out']:>9,} {r['tc']:>10,}")

    elif cmd in ("turn", "turns"):
        if not arg2:
            return print("用法: tusage turn <session_id>")
        # 匹配完整 session_id
        sid_full = None
        for row in db.execute("SELECT DISTINCT session_id FROM api_calls"):
            if row[0].endswith(arg2):
                sid_full = row[0]; break
        if not sid_full:
            return print(f"未找到 ID 尾号为 '{arg2}' 的会话。先跑 tusage list。")
        turns = db.execute(f"""
            SELECT datetime(timestamp,'unixepoch','{_TZ_OFFSET}') ts,
                   substr(turn_id,1,6) tid, model, input_tokens, output_tokens, cache_read, duration_ms
            FROM api_calls WHERE session_id=? ORDER BY timestamp DESC
        """, (sid_full,)).fetchall()
        title = title_of(sid_full)
        print(f"💬  {title or sid_full}")
        print(f"{'#':>3} {'模型':<16} {'输入':>8} {'输出':>8} {'缓存':>8} {'耗时ms':>7}")
        print("-" * 55)
        for i, r in enumerate(turns, 1):
            print(f"{i:>3} {r['model']:<16} {r['input_tokens']:>8,} {r['output_tokens']:>8,} {r['cache_read']:>8,} {r['duration_ms']:>6.0f}")
        ti = sum(r['input_tokens'] for r in turns)
        to = sum(r['output_tokens'] for r in turns)
        tc = sum(r['cache_read'] for r in turns)
        print("-" * 55)
        print(f"{'∑':>3} {ti:>8,} {to:>8,} {tc:>8,}")

    db.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)
