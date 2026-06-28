#!/usr/bin/env python3
"""usage-dash — 启动本地 Token 消耗仪表盘

用法:
  tusage-dash            # 启动网页，自动打开浏览器
  tusage-dash 8080       # 指定端口
"""
import sys, os, json, sqlite3, time, http.server, webbrowser, threading

USAGE_DB  = os.path.expanduser("~/.hermes/token-usage.db")
HERMES_DB = os.path.expanduser("~/.hermes/state.db")

_TZ_HOURS = int(time.localtime().tm_gmtoff // 3600)
_TZ_OFFSET = f"{'+' if _TZ_HOURS >= 0 else ''}{_TZ_HOURS} hours"

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8023


def title_of(sid):
    try:
        con = sqlite3.connect(HERMES_DB)
        r = con.execute("SELECT title FROM sessions WHERE id=?", (sid,)).fetchone()
        return r[0] or "" if r else ""
    except:
        return ""
    finally:
        try: con.close()
        except: pass


# ── HTML 仪表盘（单文件，含所有 CSS/JS） ─────────────────

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Token 消耗仪表盘</title>
<style>
  :root {
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --orange: #d29922; --red: #f85149;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: var(--bg); color: var(--text); padding: 24px; }
  .header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 16px; }
  h1 { font-size: 22px; font-weight: 600; }
  .sub { color: var(--muted); font-size: 13px; }

  /* ── Global filter bar ── */
  .filter-bar { display: flex; align-items: center; gap: 6px; margin-bottom: 20px; flex-wrap: wrap; }
  .filter-label { font-size: 12px; color: var(--muted); margin-right: 2px; }
  .filter-divider { color: var(--border); font-size: 13px; margin: 0 6px; }
  .fb-btn { padding: 3px 10px; border: 1px solid var(--border); border-radius: 4px; cursor: pointer; font-size: 12px; color: var(--muted); background: transparent; line-height: 1.5; }
  .fb-btn:hover { border-color: var(--accent); color: var(--accent); }
  .fb-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .fb-btn select { padding: 2px 6px; }
  .refresh-btn { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border: none; border-radius: 6px; font-size: 13px; font-weight: 500; color: var(--muted); background: transparent; line-height: 1.4; cursor: pointer; user-select: none; transition: color .15s, background .15s; }
  .refresh-btn:hover { color: var(--accent); background: rgba(88,166,255,.1); }
  .refresh-btn.spinning { pointer-events: none; color: var(--accent); }
  .refresh-btn.spinning .icon { display: inline-block; animation: spin .8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Refresh overlay ── */
  .reload-overlay { position: fixed; inset: 0; z-index: 999; display: none; align-items: center; justify-content: center; background: rgba(13,17,23,.55); backdrop-filter: blur(2px); }
  .reload-overlay.show { display: flex; }
  .reload-spinner { width: 36px; height: 36px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }

  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 16px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }
  .card h2 { font-size: 14px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 12px; }

  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
  .stat { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; text-align: center; }
  .stat .num { font-size: 28px; font-weight: 700; }
  .stat .lbl { font-size: 12px; color: var(--muted); margin-top: 4px; }
  .stat .num.green { color: var(--green); }
  .stat .num.orange { color: var(--orange); }
  .stat .num.blue { color: var(--accent); }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; padding: 8px 8px; color: var(--muted); font-weight: 500; border-bottom: 1px solid var(--border); white-space: nowrap; }
  td { padding: 8px 8px; border-bottom: 1px solid var(--border); }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  th.num { text-align: right; }
  .session-table th,
  .session-table td { text-align: center; }
  .session-table th.num,
  .session-table td.num { text-align: right; font-variant-numeric: tabular-nums; padding-right: 16px; }
  .session-table td:first-child { text-align: left; max-width: 240px; }
  .session-table th:first-child { text-align: left; }
  .session-table .sess-name { font-weight: 500; color: var(--text); cursor: pointer; }
  .session-table .sess-name:hover { color: var(--accent); }
  .session-table td { padding: 10px 6px; }
  .daily-table th,
  .daily-table td { text-align: center; }
  .daily-table th:first-child,
  .daily-table td:first-child { text-align: left; }
  .daily-table td { font-variant-numeric: tabular-nums; }
  .detail-table { width: 100%; font-size: 12px; border-collapse: collapse; }
  .detail-table th { font-size: 11px; padding: 8px 10px; white-space: nowrap; text-align: center; }
  .detail-table th:first-child,
  .detail-table td:first-child { text-align: left; padding-left: 4px; }
  .detail-table td { padding: 7px 10px; text-align: center; font-variant-numeric: tabular-nums; }
  .detail-table tr:hover td { background: rgba(88,166,255,.05); }
  .br { color: var(--green); font-weight: 600; }
  .trunc { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* ── Modal ── */
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 1000; align-items: center; justify-content: center; }
  .modal-overlay.show { display: flex; }
  .modal-box { background: var(--card); border: 1px solid var(--border); border-radius: 10px; width: min(90vw, 800px); max-height: 80vh; display: flex; flex-direction: column; }
  .modal-head { display: flex; align-items: center; padding: 16px 20px; gap: 8px; border-bottom: 1px solid var(--border); }
  .modal-head h3 { font-size: 14px; font-weight: 600; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .modal-close { cursor: pointer; color: var(--muted); font-size: 18px; line-height: 1; padding: 0 4px; }
  .modal-close:hover { color: var(--text); }
  .modal-body { padding: 12px 20px 20px; overflow-y: auto; flex: 1; }

  .badge { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 11px; font-weight: 500; }
  .badge-flash { background: #1f6feb22; color: #58a6ff; }
  .badge-pro   { background: #da363322; color: #f85149; }

  .fix-card { display: flex; flex-direction: column; min-height: 280px; }
  .fix-card .tab-wrap { flex: 1; overflow-y: auto; }

  .empty { text-align: center; padding: 40px; color: var(--muted); }
  .empty p { font-size: 14px; }

  .pg-bar { text-align: center; padding: 8px 0 0; font-size: 12px; }
  .pg-bar .pg-btn { display: inline-block; padding: 2px 8px; margin: 0 2px; border: 1px solid var(--border); border-radius: 4px; cursor: pointer; color: var(--muted); background: transparent; }
  .pg-bar .pg-btn:hover { border-color: var(--accent); color: var(--accent); }
  .pg-bar .pg-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .pg-bar .pg-info { color: var(--muted); margin: 0 8px; }
</style>
</head>
<body>

<div class="header">
  <h1>⚡ Token 消耗</h1>
  <p class="sub" id="subtitle">加载中...</p>
  <span style="flex:1"></span>
  <span class="refresh-btn" onclick="doRefresh()" title="刷新数据"><span class="icon">↻</span> 刷新</span>
</div>

<!-- Global filter bar -->
<div class="filter-bar">
  <span class="filter-label">时间</span>
  <span class="fb-btn active" data-days="7" onclick="setDays(7)">7天</span>
  <span class="fb-btn" data-days="30" onclick="setDays(30)">30天</span>
  <span class="fb-btn" data-days="0" onclick="setDays(0)">全部</span>
  <span class="filter-divider">|</span>
  <span class="filter-label">模型</span>
  <select class="fb-btn" id="modelFilter" onchange="applyModelFilter()"><option value="">全部模型</option></select>
</div>

<div class="stats" id="stats"></div>

<div class="grid">
  <div class="card fix-card">
    <h2>📅 每日趋势</h2>
    <div class="tab-wrap"><table class="daily-table"><thead><tr>
      <th>日期</th><th class="num">输入</th><th class="num">输出</th><th class="num">缓存</th><th class="num">总计</th>
    </tr></thead><tbody id="dailyTable"></tbody></table>
    <div class="pg-bar" id="dailyPg"></div></div>
  </div>
  <div class="card fix-card">
    <h2>💬 对话排行</h2>
    <div class="tab-wrap"><table class="daily-table"><thead><tr>
      <th>对话</th><th class="num">总 tokens</th>
    </tr></thead><tbody id="rankTable"></tbody></table>
    <div class="pg-bar" id="rankPg"></div></div>
  </div>
</div>

<div class="card" style="margin-top:16px">
  <h2 style="margin-bottom:12px">📋 所有对话</h2>
  <div style="overflow-x:auto"><table class="session-table"><thead><tr>
    <th>对话</th><th>模型</th><th class="num">调用</th><th class="num">输入</th><th class="num">输出</th><th class="num">缓存</th><th></th>
  </tr></thead><tbody id="sessionTable"></tbody></table></div>
  <div class="pg-bar" id="sessionPg"></div>
</div>

<script>
// ── Format ──
function fmt(n) {
  if (n >= 1_000_000) return (n/1_000_000).toFixed(2) + 'M';
  if (n >= 1_000) return (n/1_000).toFixed(1) + 'K';
  return n.toLocaleString();
}

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function fmtDuration(ms) {
  if (ms < 1000) return ms.toFixed(0) + 'ms';
  if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
  return (ms / 60000).toFixed(1) + 'm';
}

// ── 分页条生成器 ──
function renderPager(id, cur, pages, goFn) {
  document.getElementById(id).innerHTML = pages > 1
    ? `<span class="pg-btn" onclick="${goFn}(${cur-1})" style="${cur===0?'display:none':''}">‹</span><span class="pg-info">${cur+1}/${pages}</span><span class="pg-btn" onclick="${goFn}(${cur+1})" style="${cur>=pages-1?'display:none':''}">›</span>`
    : '';
}

// ── 全局状态 ──
const S = {
  days: 7,
  dailyData: [],
  rankData: [],
  allSessions: [],
  filteredSessions: null,
  store: {}  // sid -> { turns, pageSize, page }
};

// ── 数据加载 ──
async function load() {
  try {
    const [daily, sessions] = await Promise.all([
      fetch('/api/daily?days=' + S.days).then(r=>r.json()),
      fetch('/api/sessions?days=' + S.days).then(r=>r.json()),
    ]);

    const total = sessions.reduce((s, r) => s + r.ti + r.tok_out + r.tc, 0);
    document.getElementById('subtitle').textContent =
      `${sessions.length} 个对话 · 合计 ${fmt(total)} tokens`;

    const calls = sessions.reduce((s, r) => s + r.calls, 0);
    const inp = sessions.reduce((s, r) => s + r.ti, 0);
    const out = sessions.reduce((s, r) => s + r.tok_out, 0);
    const cache = sessions.reduce((s, r) => s + r.tc, 0);
    document.getElementById('stats').innerHTML = `
      <div class="stat"><div class="num blue">${calls}</div><div class="lbl">API 调用</div></div>
      <div class="stat"><div class="num orange">${fmt(inp)}</div><div class="lbl">输入 tokens</div></div>
      <div class="stat"><div class="num green">${fmt(out)}</div><div class="lbl">输出 tokens</div></div>
      <div class="stat"><div class="num" style="color:var(--orange)">${fmt(cache)}</div><div class="lbl">缓存 tokens</div></div>
    `;

    S.dailyData = daily;
    S.rankData = sessions;
    S.allSessions = sessions;
    S.filteredSessions = null;

    const models = [...new Set(sessions.map(s => s.model).filter(Boolean))];
    const sel = document.getElementById('modelFilter');
    sel.innerHTML = '<option value="">全部模型</option>' + models.map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join('');

    renderDaily(0);
    renderRank(0);
    renderSession(0);
  } catch (e) {
    document.getElementById('subtitle').textContent = '⚠ 加载失败: ' + e.message;
  } finally {
    document.getElementById('reloadOverlay').classList.remove('show');
    document.querySelector('.refresh-btn').classList.remove('spinning');
  }
}

// ── 每日趋势（分页） ──
function renderDaily(page) {
  const ps = 5;
  const total = S.dailyData.length;
  const pages = Math.ceil(total / ps) || 1;
  const cur = Math.min(page, pages - 1);
  const slice = S.dailyData.slice(cur * ps, (cur + 1) * ps);
  document.getElementById('dailyTable').innerHTML = slice.map(r => {
    const tot = r.ti + r.tok_out + r.tc;
    return `<tr><td>${r.day}</td><td class="num">${fmt(r.ti)}</td><td class="num">${fmt(r.tok_out)}</td><td class="num">${fmt(r.tc)}</td><td class="num">${fmt(tot)}</td></tr>`;
  }).join('');
  renderPager('dailyPg', cur, pages, 'renderDaily');
}

// ── 对话排行（分页） ──
function renderRank(page) {
  const ps = 5;
  const total = S.rankData.length;
  const pages = Math.ceil(total / ps) || 1;
  const cur = Math.min(page, pages - 1);
  const slice = S.rankData.slice(cur * ps, (cur + 1) * ps);
  document.getElementById('rankTable').innerHTML = slice.map(s => {
    const title = s.title || s.sid.slice(-14);
    const tot = s.ti + s.tok_out + s.tc;
    return `<tr><td class="trunc">${esc(title)}</td><td class="num">${fmt(tot)}</td></tr>`;
  }).join('');
  renderPager('rankPg', cur, pages, 'renderRank');
}

// ── 所有对话（分页） ──
function renderSession(page) {
  const data = S.filteredSessions || S.allSessions;
  const ps = 5;
  const total = data.length;
  const pages = Math.ceil(total / ps) || 1;
  const cur = Math.min(page, pages - 1);
  const slice = data.slice(cur * ps, (cur + 1) * ps);
  document.getElementById('sessionTable').innerHTML = slice.map(s => {
    const title = s.title || s.sid.slice(-14);
    const badgeClass = s.model && s.model.includes('pro') ? 'badge-pro' : 'badge-flash';
    return `<tr>
      <td class="sess-name" onclick="openModal('${s.sid}', '${esc(title)}')">${esc(title)}</td>
      <td><span class="badge ${badgeClass}">${esc(s.model||'')}</span></td>
      <td class="num">${s.calls}</td><td class="num">${fmt(s.ti)}</td><td class="num">${fmt(s.tok_out)}</td>
      <td class="num">${fmt(s.tc)}</td>
      <td><span style="color:var(--muted);font-size:11px;cursor:pointer" onclick="openModal('${s.sid}', '${esc(title)}')">▶</span></td>
    </tr>`;
  }).join('');
  renderPager('sessionPg', cur, pages, 'renderSession');
}

// ── 筛选逻辑 ──
function setDays(d) {
  S.days = d;
  document.querySelectorAll('.filter-bar .fb-btn[data-days]').forEach(b => b.classList.toggle('active', parseInt(b.dataset.days) === d));
  load();
}

function applyModelFilter() {
  const model = document.getElementById('modelFilter').value;
  filterSessionTable(model);
}

function filterSessionTable(model) {
  S.filteredSessions = model
    ? S.allSessions.filter(s => s.model === model)
    : null;
  S.rankData = S.filteredSessions || S.allSessions;
  renderRank(0);
  renderSession(0);
}

// ── Modal ──
function openModal(sid, title) {
  document.getElementById('modalTitle').textContent = title;
  document.getElementById('modalOverlay').classList.add('show');
  if (!S.store[sid]) {
    fetch('/api/turns/' + encodeURIComponent(sid)).then(r => r.json()).then(turns => {
      S.store[sid] = { turns, pageSize: 5, page: 0 };
      renderDetail(sid);
    });
  } else {
    renderDetail(sid);
  }
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('show');
}

function renderDetail(sid) {
  const st = S.store[sid];
  const { turns, pageSize, page } = st;
  const total = turns.length;
  const pages = Math.ceil(total / pageSize) || 1;
  const cur = Math.min(page, pages - 1);
  st.page = cur;
  const slice = turns.slice(cur * pageSize, (cur + 1) * pageSize);

  let html = '<table class="detail-table"><thead><tr><th>#</th><th>时间</th><th>模型</th><th class="num">输入</th><th class="num">输出</th><th class="num">缓存</th><th class="num">耗时</th></tr></thead><tbody>';
  slice.forEach((t, i) => {
    const n = cur * pageSize + i + 1;
    html += `<tr><td>${n}</td><td style="white-space:nowrap;font-size:11px;color:var(--muted)">${t.ts.slice(0,16)}</td><td>${esc(t.model||'')}</td><td class="num">${fmt(t.input_tokens)}</td><td class="num">${fmt(t.output_tokens)}</td><td class="num">${fmt(t.cache_read)}</td><td class="num">${fmtDuration(t.duration_ms)}</td></tr>`;
  });
  html += '</tbody></table>';

  if (pages > 1) {
    html += '<div class="pg-bar">';
    if (cur > 0) html += `<span class="pg-btn" onclick="goPage('${sid}', ${cur-1})">‹</span>`;
    html += `<span class="pg-info">${cur+1}/${pages}</span>`;
    if (cur < pages - 1) html += `<span class="pg-btn" onclick="goPage('${sid}', ${cur+1})">›</span>`;
    html += '</div>';
  }

  document.getElementById('modalBody').innerHTML = html;
}

function goPage(sid, p) {
  S.store[sid].page = p;
  renderDetail(sid);
}

function doRefresh() {
  document.getElementById('reloadOverlay').classList.add('show');
  document.querySelector('.refresh-btn').classList.add('spinning');
  load();
}

load(); // 初始加载
</script>

<!-- Modal -->
<div class="modal-overlay" id="modalOverlay" onclick="closeModal()">
  <div class="modal-box" onclick="event.stopPropagation()">
    <div class="modal-head">
      <h3 id="modalTitle">会话详情</h3>
      <span class="modal-close" onclick="closeModal()">✕</span>
    </div>
    <div class="modal-body" id="modalBody"></div>
  </div>
</div>

<div class="reload-overlay" id="reloadOverlay"><div class="reload-spinner"></div></div>

</body></html>"""

# ── API 服务器 ──────────────────────────────────────────

def get_data(days=7):
    db = sqlite3.connect(USAGE_DB)
    db.row_factory = sqlite3.Row
    since = 0.0 if days == 0 else time.time() - days * 86400

    daily = db.execute(
        f"SELECT date(datetime(timestamp,'unixepoch','{_TZ_OFFSET}')) day, "
        "sum(input_tokens) ti, sum(output_tokens) tok_out, sum(cache_read) tc "
        "FROM api_calls WHERE timestamp>=? GROUP BY day ORDER BY day DESC",
        (since,)
    ).fetchall()
    sessions_raw = db.execute(
        "SELECT session_id sid, min(model) model, count(*) calls, "
        "sum(input_tokens) ti, sum(output_tokens) tok_out, sum(cache_read) tc, "
        "min(timestamp) first_ts "
        "FROM api_calls WHERE timestamp>=? "
        "GROUP BY sid ORDER BY max(timestamp) DESC",
        (since,)
    ).fetchall()
    db.close()

    sessions = []
    for r in sessions_raw:
        d = dict(r)
        d['title'] = title_of(d['sid'])
        sessions.append(d)

    return {"daily": [dict(r) for r in daily], "sessions": sessions}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0]
        qs = {}
        if '?' in self.path:
            for p in self.path.split('?')[1].split('&'):
                if '=' in p:
                    k, v = p.split('=', 1)
                    qs[k] = v
        days = int(qs.get('days', 7))

        if path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html;charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML.encode('utf-8'))
            return

        data = get_data(days)
        if path == '/api/daily':
            self._json(data['daily'])
        elif path == '/api/sessions':
            self._json(data['sessions'])
        elif path.startswith('/api/turns/'):
            sid = self.path.split('?')[0][11:]
            db = sqlite3.connect(USAGE_DB)
            db.row_factory = sqlite3.Row
            rows = db.execute(
                f"SELECT datetime(timestamp,'unixepoch','{_TZ_OFFSET}') ts, model, input_tokens, output_tokens, cache_read, duration_ms FROM api_calls WHERE session_id=? ORDER BY timestamp DESC",
                (sid,)
            ).fetchall()
            db.close()
            self._json([dict(r) for r in rows])
        else:
            self._json({"error": "not found"}, 404)

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json;charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def main():
    if not os.path.exists(USAGE_DB):
        print("（暂无数据，新会话跑几轮后再启动仪表盘）")
        return
    port = PORT
    for attempt in range(100):
        try:
            server = http.server.HTTPServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            port += 1
    else:
        print(f"❌ 无法找到可用端口（{PORT}–{PORT+99} 均被占用）")
        return
    webbrowser.open(f'http://127.0.0.1:{port}')
    print(f"⚡ 仪表盘已启动: http://127.0.0.1:{port}")
    print("   按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
