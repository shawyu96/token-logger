# Token Logger

> Hermes Agent 插件 — 按次记录 LLM API 调用的真实 token 消耗，提供 CLI 查询和 Web 仪表盘。

---

## 目录

- [快速开始](#快速开始)
- [CLI 参考](#cli-参考)
- [Web 仪表盘](#web-仪表盘)
- [数据库](#数据库)
- [架构](#架构)
- [文件清单](#文件清单)
- [故障排查](#故障排查)
- [维护](#维护)

---

## 快速开始

### 前置依赖

- Hermes Agent（桌面版或 CLI）
- Python 3.11+
- 已运行若干轮对话（有数据可查）

### 1. 安装插件

```bash
# 确认插件已安装
ls ~/.hermes/plugins/token-logger/

# 启用（如未自动加载）
hermes plugins enable token-logger

# ⚠ 插件激活需要重启 Hermes daemon
# 桌面版：退出重新打开
# CLI 版：hermes chat — 新会话自动加载
```

### 2. 配置别名（一次性）

```bash
# 加到 ~/.zshrc（如果还没有）
echo 'alias tusage="python3 ~/.hermes/plugins/token-logger/query.py"' >> ~/.zshrc
echo 'alias tusage-dash="python3 ~/.hermes/plugins/token-logger/usage-dash.py"' >> ~/.zshrc
source ~/.zshrc
```

### 3. 验证

```bash
# 查看今日汇总
tusage daily

# 启动仪表盘
tusage-dash
```

---

## CLI 参考

所有命令均从 `token-usage.db` 直接读取，无需 Hermes 运行中。

```
tusage daily [天数]          每日汇总（默认 7 天）
tusage session [天数]        按对话汇总
tusage list [天数]           列出所有会话
tusage turn <会话ID>         查看单次对话的逐条调用明细
tusage --help                显示帮助
```

### 示例

```bash
# 最近 7 天每日汇总
tusage daily
# 输出：
# 日期        次数       输入        输出          缓存
# --------------------------------------------------
# 2026-06-29   15    152,300     25,400      12,100
# 2026-06-28   42  1,200,000    380,000      95,000
# --------------------------------------------------
# ∑            57  1,352,300    405,400     107,100

# 最近 30 天按对话排名
tusage session 30

# 列出所有会话（含 ID 尾号）
tusage list

# 查看某个会话的每次调用
tusage turn aBcDeF123Xyz
```

### 常用技巧

- `tusage daily 0` — 全部历史
- `tusage session 1` — 仅今天
- 会话 ID 支持尾号匹配，不用复制完整 UUID

---

## Web 仪表盘

### 启动

```bash
tusage-dash              # 默认端口 8023
tusage-dash 9090         # 指定端口
```

自动打开浏览器。端口被占用时自动递增搜索（最多 100 个）。

### 界面

```
┌─ ⚡ Token 消耗 ──────────────────────── [↻ 刷新] ─┐
│   15 个对话 · 合计 1.35M tokens                     │
│                                                     │
│  [时间: 7天 | 30天 | 全部] | [模型: ▼全部模型]      │
│                                                     │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌──────────┐        │
│  │  57      │  │  1.35M     │  │  405K    │  │  108K   │        │
│  │ API 调用 │  │ 输入 tokens│  │ 输出     │  │ 缓存    │        │
│  └──────────┘  └────────────┘  └──────────┘  └──────────┘        │
│                                                     │
│  ┌─ 每日趋势 ─────┐  ┌─ 对话排行 ──────────┐       │
│  │ 日期  输入 ... │  │ 对话        总 tokens│       │
│  │ 06-29 152K ...│  │ 代码审查     890K    │       │
│  │ ‹ 1/5 ›       │  │ ‹ 1/4 ›             │       │
│  └────────────────┘  └──────────────────────┘       │
│                                                     │
│  ┌─ 所有对话 ──────────────────────────────── ─┐   │
│  │ 对话        模型   调用  输入  输出  缓存    │   │
│  │ 代码审查    flash   15   89K  12K   3K  ▶  │   │
│  │ ...                                        │   │
│  │ ‹ 1/4 ›                                    │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 功能清单

| 区域 | 功能 |
|------|------|
| **统计卡片** | API 调用数、输入 tokens、输出 tokens、缓存 tokens |
| **每日趋势** | 按日汇总，分页 5 条，倒序排列 |
| **对话排行** | 按 token 总量降序排列（当前筛选数据下） |
| **所有对话** | 分页 5 条，按最后活跃时间倒序排列，点选查看详情 |
| **会话详情弹窗** | 每次调用的：序号、时间、模型、输入/输出/缓存、耗时（动态单位 ms/s/m），最新在前倒序排列 |
| **全局筛选栏** | 时间范围（7天/30天/全部）+ 模型精确匹配 |
| **↻ 刷新** | 全屏加载动画，数据重新拉取 |

### 弹窗功能

点击任意对话名称（蓝色高亮）或 ▶ 按钮，弹出详情窗口，展示该会话的每次 API 调用记录：

| 列 | 说明 |
|----|------|
| `#` | 调用序号 |
| 时间 | 精确到分，左对齐 |
| 模型 | 模型名称 |
| 输入/输出/缓存 | token 数，居中，等宽数字 |
| 耗时 | 毫秒，居中 |

弹窗支持分页（5 条/页）和点击遮罩关闭。

---

## 数据库

### 位置

```
~/.hermes/token-usage.db       — 调用记录（主数据）
~/.hermes/state.db              — Hermes 会话元信息（只读，仅查标题）
```

### 表结构

```sql
CREATE TABLE api_calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     REAL NOT NULL,                -- Unix 时间戳
    session_id    TEXT NOT NULL,                -- Hermes 会话 UUID
    turn_id       TEXT DEFAULT '',
    api_req_id    TEXT DEFAULT '',
    model         TEXT NOT NULL,                -- 模型名（如 deepseek-v4-flash）
    provider      TEXT DEFAULT '',              -- 提供商
    input_tokens  INTEGER DEFAULT 0,            -- 输入 tokens
    output_tokens INTEGER DEFAULT 0,            -- 输出 tokens
    cache_read    INTEGER DEFAULT 0,            -- 缓存命中 tokens
    cache_write   INTEGER DEFAULT 0,            -- 缓存写入 tokens
    reasoning     INTEGER DEFAULT 0,            -- 推理 tokens
    duration_ms   REAL DEFAULT 0.0,             -- 耗时（毫秒）
    finish_reason TEXT DEFAULT '',              -- stop / length 等
    raw_usage     TEXT DEFAULT ''               -- API 原始 usage JSON
);
```

### 索引

```sql
CREATE INDEX idx_api_calls_session ON api_calls(session_id, timestamp);
CREATE INDEX idx_api_calls_time ON api_calls(timestamp);
```

### 查询示例

```sql
-- 某会话按模型汇总
SELECT model, count(*), sum(input_tokens), sum(output_tokens)
FROM api_calls WHERE session_id='xxx' GROUP BY model;

-- 今日各模型消耗
SELECT model, sum(input_tokens + output_tokens) AS total
FROM api_calls WHERE timestamp >= unixepoch('now', 'start of day')
GROUP BY model ORDER BY total DESC;

-- 最近 50 次缓存命中率
SELECT count(*), sum(CASE WHEN cache_read > 0 THEN 1 ELSE 0 END) AS cached
FROM api_calls ORDER BY timestamp DESC LIMIT 50;
```

---

## 架构

```
                    ┌─────────────────────┐
                    │   Hermes Agent      │
                    │   (每次 API 调用后)  │
                    └─────────┬───────────┘
                              │ post_api_request hook
                              ▼
                    ┌─────────────────────┐
                    │   __init__.py       │
                    │   (写入 token-usage) │
                    └─────────┬───────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │  token-usage.db     │
                    │  (本地 SQLite)       │
                    └──────┬──────────────┘
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
     ┌────────────┐ ┌───────────┐ ┌──────────────┐
     │ query.py   │ │usage-dash │ │ 其他工具     │
     │ (tusage)   │ │(仪表盘)   │ │(SQL 直查等)  │
     └────────────┘ └───────────┘ └──────────────┘
```

**设计原则：**
- 插件只写不读，查询工具独立于 Hermes 运行
- SQLite 文件可交叉验证（对比 API 原始 usage）
- 仪表盘为单文件全栈（Python 后端 + 内嵌 HTML/CSS/JS）

---

## 文件清单

```
token-logger/
├── README.md          本文档
├── __init__.py        插件核心 — hook 注册、数据库写入（123 行）
├── plugin.yaml        插件元信息（名称、版本、hook 声明）
├── query.py           tusage CLI — 终端查询工具（122 行）
└── usage-dash.py      tusage-dash — Web 仪表盘（511 行，单文件全栈）
```

---

## 故障排查

### 仪表盘启动报 "Address already in use"

端口被占，自动递增搜索。手动杀死旧进程：

```bash
lsof -ti :8023 | xargs kill -9
tusage-dash
```

### 仪表盘显示 "暂无数据"

插件可能未激活或 Hermes 未重启：

```bash
# 检查插件状态
hermes plugins list | grep token-logger

# 确认数据库有数据
sqlite3 ~/.hermes/token-usage.db "SELECT count(*) FROM api_calls"
```

### CLI 中文显示乱码

确认终端支持 UTF-8：

```bash
export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8
```

### 仪表盘筛选后没有数据

模型筛选为**精确匹配**。如果模型名是 `deepseek-v4-flash`，选 `deepseek-v4-flash-pro` 不会匹配到。确认下拉框中的模型名。

---

## 维护

### 清理旧数据

```bash
# 删除 90 天前的记录
sqlite3 ~/.hermes/token-usage.db \
  "DELETE FROM api_calls WHERE timestamp < unixepoch('now', '-90 days')"

# 清理后压缩数据库
sqlite3 ~/.hermes/token-usage.db "VACUUM"
```

### 备份

```bash
cp ~/.hermes/token-usage.db ~/backups/token-usage-$(date +%Y%m%d).db
```

### 数据保留策略

默认不自动删除，所有历史完整保留。可根据需要添加 cron 定期清理。

### 升级

```bash
# 替换插件文件
cp -r token-logger/ ~/.hermes/plugins/token-logger/
# 重启 Hermes daemon 使新代码生效
```

---

## 技术细节

| 项目 | 说明 |
|------|------|
| 时区 | 自动读取系统 `tm_gmtoff`，无需手动配置 |
| 端口 | 默认 8023，被占用时自动递增（最多 100 个） |
| 并发 | 数据库写操作用 `threading.Lock` 保护 |
| SQL 安全 | 全部参数化查询，无拼接 |
| XSS 防护 | 前端使用 `textContent` + `esc()` 双重保护 |
| 浏览器兼容 | 现代浏览器（Chrome / Firefox / Safari / Edge） |

---

## License

MIT
