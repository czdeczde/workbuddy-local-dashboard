---
name: workbuddy-local-dashboard
display_name: "WorkBuddy 本地算力看板"
display_name_en: "WorkBuddy Local Dashboard"
description: 在本机启动一个 WorkBuddy 算力看板（会话数、上下文、积分、Token、天气空气质量、微博热搜、今日热榜、股指），用量数据只在本机读取，天气/热榜/股指走公开接口，自动探测本机 workbuddy.db 无需配置，每 30 分钟自动刷新。另含番茄时钟与喝水记录。当用户说"看板""算力看板""启动看板""打开看板""本地看板""dashboard""查看我的用量"或想看本机 WorkBuddy 用量与实时热点时使用。
description_zh: 在本机启动一个 WorkBuddy 算力看板，显示会话数、上下文占用、积分余额、Token 累计、天气与空气质量、微博热搜、今日头条热榜、三大股指，另含番茄时钟与喝水记录。用量数据只在本机读取，公开数据走网络接口，自动探测数据库，每 30 分钟自动刷新。触发词：看板、算力看板、启动看板、打开看板、dashboard、查看我的用量。
description_en: Launch a WorkBuddy dashboard on the local machine showing session count, context usage, credits, token usage, weather & air quality, Weibo hot search, Toutiao trending, major indices, plus a Pomodoro timer and water tracker. Usage data stays local; public data comes from open APIs. Auto-detects workbuddy.db, refreshes every 30 minutes.
version: "2.1.0"
---

# WorkBuddy 本地算力看板（免费版）

一个双击即用的本机看板：WorkBuddy 用量（会话 / 上下文 / 积分 / Token）+ 广州实况天气与空气质量 + 微博热搜 + 今日头条热榜 + 三大股指。**用量数据不出本机**，无需 NAS、无需云服务、无需配置数据库路径。

## 2.1.0 更新

- 看板升级为五列布局，新增番茄时钟（25/5 分钟，专注完成与休息完成有简单提示音，可一键开关）与喝水记录（成年男性建议 1700ml/天，+250ml 累加，按日自动清空）。
- 提示音开关、番茄计数、喝水量保存在浏览器 localStorage，换浏览器或清缓存会重置。
- 官方提交版已清空个人快照数据，首次启动后由脚本回写真实数据。

## 何时使用

用户提到「看板 / 算力看板 / 启动看板 / 打开看板 / 本地看板 / dashboard / 看我的用量」时触发。

## 核心原则（必须遵守）

### 1. last_snapshot 合并机制
- **所有数据输出必须以 `assets/snapshot.json` 为底**，新抓取的数据与旧快照合并后输出
- 新数据成功 → 用新值替换对应字段
- 新数据失败 → 保留旧值，并在结果中标注 `stale_reason: "保留上次快照值"`
- **禁止直接输出 raw 抓取数据**，必须经过合并

### 2. 单一入口原则
- **禁止直接调用 `fetch_external` 底层函数**
- 所有数据获取必须通过 `dashboard.refresh()` 或 `refresh_once.py`
- 底层抓取函数仅供内部使用，不对外暴露

### 3. 超时与降级
- 单次刷新总超时：**60 秒**
- 单个外部接口超时：**20 秒**
- 超时或失败时立即返回部分结果，不阻塞整轮

### 4. 数据来源标注
- 每个数据字段必须包含 `source`（来源）和 `collected`（采集时间）
- 失败数据必须标注 `stale_reason`，不得留空

## 快速启动

在技能目录下运行（Windows 可直接双击 `启动看板.bat`）：

```bash
python scripts/dashboard.py --port 8901
```

随后用浏览器打开 `http://127.0.0.1:8901/`。

启动脚本会：
1. 自动探测本机 `workbuddy.db`（依次尝试环境变量 `WORKBUDDY_DB`、技能目录附近、`~/.workbuddy/`、用户目录浅层扫描）；
2. 立即拉一次真实数据并回写 `assets/dashboard.html` 里的 `const DATA` 块；
3. 同时更新 `assets/snapshot.json`（last_snapshot 文件）；
4. 启动本机 HTTP 服务，并开一个后台线程每 30 分钟自动刷新；
5. 页面端每 30 分钟也静默请求一次 `/api/refresh`，双保险。

## 手动 / 按需操作

| 操作 | 命令 | 说明 |
|------|------|------|
| 单次刷新 | `python scripts/refresh_once.py` | 合并 last_snapshot 后输出，超时 60s |
| 导出文档 | `python scripts/export_data.py --format md` | 生成 Markdown 交付文档 |
| 指定数据库 | `python scripts/refresh_once.py --db "D:/path/to/workbuddy.db"` | 自动探测失败时使用 |
| 查看快照 | 读取 `assets/snapshot.json` | last_snapshot 文件，供合并参考 |

## 数据契约（严格约束）

### 输入
- 看板所有内容来自 `assets/dashboard.html` 中的 `const DATA = {...};`，由脚本回写
- 用量指标来自本机 `workbuddy.db`（只读 `mode=ro`），表结构随版本变化时做字段容错
- last_snapshot 文件：`assets/snapshot.json`，格式与 DATA 块一致

### 输出
- **合并规则**：新数据 + 旧快照 → 输出结果
  - 新数据成功 → 替换字段 + 标注 `source`、`collected`
  - 新数据失败 → 保留旧值 + 标注 `stale_reason`
- **禁止行为**：
  - 不得硬编码默认值（如 `creditBalance: 3251.799`）
  - 不得吞掉异常后静默跳过（必须记录 `stale_reason`）
  - 不得绕过 `dashboard.refresh()` 直接拼装数据

### 字段容错
- DB 字段缺失 → 给 `null` + 标注 `note: "字段缺失"`
- 外部接口失败 → 保留旧值 + 标注 `stale_reason`
- 网络超时 → 保留旧值 + 标注 `stale_reason: "超时"`

## 文件结构

```
workbuddy-local-dashboard/
├── SKILL.md                     # 本文件
├── 启动看板.bat                  # 双击启动
├── scripts/
│   ├── dashboard.py             # 本机服务 + 30分钟自动刷新（唯一合并入口）
│   ├── refresh_once.py          # 单次刷新（调用 dashboard.refresh）
│   ├── export_data.py           # 数据导出为 Markdown/JSON
│   ├── db_probe.py              # 自动探测 workbuddy.db
│   ├── db_query.py              # 只读查询 + 字段容错
│   └── fetch_external.py        # 外部真实数据抓取（仅内部调用）
└── assets/
    ├── dashboard.html           # 看板页面（含 const DATA 块）
    └── snapshot.json            # last_snapshot（合并底稿）
```

## 隐私与边界

- 服务默认只监听 `127.0.0.1`，不对外网卡开放，数据库只读；如需局域网访问须显式传 `--host 0.0.0.0`
- 首启门禁密码、出生日期保存在浏览器 localStorage，仅防随手打开，不是加密
- 外部接口仅用于读取公开数据，若所在网络不可达会自动保留旧值，不影响看板打开
- **用量数据不出本机**；天气、热榜、股指需联网从公开接口读取，接口不可达时保留上次值

## 常见问题排查

| 现象 | 原因 | 解法 |
|------|------|------|
| 启动报「找不到 python」 | 系统 PATH 中无 python 命令 | 用本机 Python 完整路径运行，例如 `<python安装目录>\python.exe scripts/dashboard.py` |
| 数据库未找到 | 自动探测失败(路径不在白名单) | 设置环境变量 `WORKBUDDY_DB="D:/path/to/workbuddy.db"` 后重启 |
| 端口被占用 | 8901 端口已有进程 | 换端口:`python scripts/dashboard.py --port 8902` |
| 所有外部数据失败 | 网络不可达或 API 限流 | 查看 `assets/snapshot.json` 中的 `stale_reason`，下次刷新会重试 |
| 刷新超时 | 外部接口响应慢 | 单次刷新已设 60s 超时，超时后返回部分结果 |
| 导出文档为空 | DB 查询失败 | 检查 `--db` 参数是否正确指定 |
