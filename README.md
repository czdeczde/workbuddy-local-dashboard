# WorkBuddy 本地算力看板

双击即用的本机看板：**WorkBuddy 用量**（会话 / 上下文 / 积分 / Token）+ 天气与空气质量 + 微博热搜 + 今日头条热榜 + 三大股指，另含番茄时钟与喝水记录。

**用量数据只在本机读取**，不上传、不依赖 NAS 或云服务；公开数据（天气 / 热榜 / 股指）走公开接口，自动探测本机 `workbuddy.db`，无需配置数据库路径，每 30 分钟自动刷新。

> 这是一个 [WorkBuddy](https://www.workbuddy.cn/) Skill 包，可直接放进技能的 `skills/` 目录使用。

## 功能

- **用量看板**：今日会话数、上下文占用、积分余额、Token 累计、会话状态分布
- **环境信息**：实时天气 / AQI、微博热搜、今日头条热榜、三大股指
- **效率工具**：番茄时钟（25/5 分钟，可开关提示音）、喝水记录、每日待办、人生进度条
- **自动刷新**：服务端每 30 分钟拉一次 + 页面端静默请求 `/api/refresh`，双保险
- **快照合并**：新数据失败时保留上次快照并标注 `stale_reason`，不影响看板打开

## 快速开始

**Windows**：双击 `启动看板.bat`，浏览器会自动打开 `http://127.0.0.1:<端口>/`。脚本自动探测 8901–8910 的空闲端口。

**命令行**：

```bash
python scripts/dashboard.py --port 8901
```

可选参数：

| 参数 | 说明 |
|------|------|
| `--port` | 端口，默认 8901 |
| `--host` | 监听地址，默认 `127.0.0.1`（仅本机）；需局域网访问时显式传 `0.0.0.0` |
| `--db` | 显式指定 `workbuddy.db` 路径，自动探测失败时用 |

其他操作：

```bash
python scripts/refresh_once.py            # 单次刷新（合并快照后输出，超时 60s）
python scripts/export_data.py --format md # 导出 Markdown 交付文档
```

## 安装为 WorkBuddy Skill

把本仓库目录整个复制到 WorkBuddy 的 `skills/` 目录下（目录名保持 `workbuddy-local-dashboard`），重启会话后说「启动看板」即可触发。

## 隐私与安全

- 服务**默认只监听 `127.0.0.1`**，不对外网卡开放；数据库以只读模式 `mode=ro` 打开
- 用量数据不出本机；天气 / 热榜 / 股指需联网读取，接口不可达时自动保留上次值
- 首启门禁密码、番茄计数、喝水量、生日等保存在浏览器 `localStorage`，仅防随手打开，不是加密
- 仓库内 `assets/snapshot.json` 为空白快照，首次启动后由脚本回写真实数据

## 目录结构

```
workbuddy-local-dashboard/
├── SKILL.md                  # Skill 定义与使用说明
├── 启动看板.bat               # Windows 双击启动
├── scripts/
│   ├── dashboard.py          # 本机服务 + 30 分钟自动刷新（唯一合并入口）
│   ├── refresh_once.py       # 单次刷新
│   ├── export_data.py        # 导出 Markdown / JSON
│   ├── db_probe.py           # 自动探测 workbuddy.db
│   ├── db_query.py           # 只读查询 + 字段容错
│   └── fetch_external.py     # 公开数据抓取（仅内部调用）
└── assets/
    ├── dashboard.html        # 看板页面（含 const DATA 数据块）
    └── snapshot.json         # 空白快照（合并底稿）
```

## 环境要求

Python 3.x，无需第三方依赖（全部使用标准库）。Windows 系统自带的 `python` 可能是 Windows Store 占位符，先用 `where.exe python` 确认指向真实安装。

## 许可证

MIT
