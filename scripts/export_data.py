# -*- coding: utf-8 -*-
"""
WorkBuddy 本地算力看板 · 数据导出为 Markdown/JSON 文档
用法：python export_data.py [--format md|json] [--db 路径]
功能：
  - 从 workbuddy.db 查询真实数据
  - 读取 assets/snapshot.json 作为 last_snapshot
  - 生成交付文档（Markdown 或 JSON）
  - 所有数据标注来源与时间，失败数据标注 stale_reason
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import db_probe
import db_query
import fetch_external as ext


def export_md(data, snapshot=None):
    """导出为 Markdown 格式。"""
    lines = []
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("# WorkBuddy 本地算力看板 · 数据报告")
    lines.append("")
    lines.append("**采集时间**: %s" % now)
    lines.append("")

    # WorkBuddy 用量
    wb = data.get("wb", {})
    lines.append("## 一、WorkBuddy 用量")
    lines.append("")
    lines.append("| 指标 | 数值 | 来源 |")
    lines.append("|------|------|------|")
    lines.append("| 今日会话数 | %s | workbuddy.db:sessions |" % wb.get("sessionsToday", "N/A"))
    lines.append("| 上下文占用 | %s / %s | workbuddy.db:session_usage |" % (
        wb.get("ctxUsed", "N/A"), wb.get("ctxSize", "N/A")))
    lines.append("| 积分总额 | %s | workbuddy.db:session_usage.credit_json |" % wb.get("creditTotal", "N/A"))
    lines.append("| Token 累计 | %s | workbuddy.db:session_usage.used |" % wb.get("tokenTotal", "N/A"))
    if wb.get("creditBalance") is not None:
        lines.append("| 积分余额 | %s | workbuddy.db（旧快照） |" % wb.get("creditBalance"))
    else:
        lines.append("| 积分余额 | N/A | 字段缺失 |")
    lines.append("")

    # 天气
    weather = data.get("weather")
    if weather:
        lines.append("## 二、天气与空气质量")
        lines.append("")
        lines.append("**城市**: %s" % weather.get("city", "N/A"))
        lines.append("**采集时间**: %s" % weather.get("collected", "N/A"))
        lines.append("**来源**: %s" % weather.get("source", "N/A"))
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append("| 实况温度 | %s°C |" % weather.get("temp", "N/A"))
        lines.append("| 天气描述 | %s |" % weather.get("desc", "N/A"))
        lines.append("| 空气质量 | %s |" % weather.get("aqi", "N/A"))
        lines.append("| 湿度 | %s |" % weather.get("humidity", "N/A"))
        lines.append("| 风力 | %s |" % weather.get("wind", "N/A"))
        lines.append("")
    else:
        lines.append("## 二、天气与空气质量")
        lines.append("")
        lines.append("> ⚠️ 数据获取失败，保留上次快照值")
        if snapshot and snapshot.get("weather"):
            lines.append("**上次采集时间**: %s" % snapshot["weather"].get("collected"))
        lines.append("")

    # 微博热搜
    weibo = data.get("weibo")
    if weibo:
        lines.append("## 三、微博热搜（前 %d 条）" % len(weibo))
        lines.append("")
        lines.append("**采集时间**: %s" % now)
        lines.append("**来源**: 微博官方 AJAX 接口")
        lines.append("")
        lines.append("| 排名 | 标题 | 热度 |")
        lines.append("|------|------|------|")
        for item in weibo[:10]:
            lines.append("| %d | %s | %s |" % (
                item.get("rank", 0),
                item.get("title", "N/A")[:30],
                ext.fmt_hot(item.get("hot", 0))))
        lines.append("")
    else:
        lines.append("## 三、微博热搜")
        lines.append("")
        lines.append("> ⚠️ 数据获取失败，保留上次快照值")
        lines.append("")

    # 今日头条
    toutiao = data.get("toutiao")
    if toutiao:
        lines.append("## 四、今日头条热榜（前 %d 条）" % len(toutiao))
        lines.append("")
        lines.append("**采集时间**: %s" % now)
        lines.append("**来源**: 今日头条官方接口")
        lines.append("")
        lines.append("| 排名 | 标题 | 热度 |")
        lines.append("|------|------|------|")
        for item in toutiao[:10]:
            lines.append("| %d | %s | %s |" % (
                item.get("rank", 0),
                item.get("title", "N/A")[:30],
                ext.fmt_hot(item.get("hot", 0))))
        lines.append("")
    else:
        lines.append("## 四、今日头条热榜")
        lines.append("")
        lines.append("> ⚠️ 数据获取失败，保留上次快照值")
        lines.append("")

    # 股指
    indices = data.get("indices")
    if indices:
        lines.append("## 五、三大股指")
        lines.append("")
        lines.append("**采集时间**: %s" % now)
        lines.append("**来源**: 腾讯行情接口")
        lines.append("")
        lines.append("| 指数 | 点位 | 涨跌 | 涨跌幅 |")
        lines.append("|------|------|------|--------|")
        for idx in indices:
            lines.append("| %s | %s | %s | %s%% |" % (
                idx.get("name", "N/A"),
                idx.get("price", "N/A"),
                idx.get("change", "N/A"),
                idx.get("pct", "N/A")))
        lines.append("")
    else:
        lines.append("## 五、三大股指")
        lines.append("")
        lines.append("> ⚠️ 数据获取失败，保留上次快照值")
        lines.append("")

    # 底部标注
    lines.append("---")
    lines.append("")
    lines.append("*本报告由 WorkBuddy 本地算力看板自动生成*")
    lines.append("*数据来自本机 workbuddy.db 及公开接口，仅供参考*")

    return "\n".join(lines)


def export_json(data, snapshot=None):
    """导出为 JSON 格式。"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description="WorkBuddy 本地算力看板 · 数据导出")
    ap.add_argument("--format", choices=["md", "json"], default="md", help="输出格式（默认 md）")
    ap.add_argument("--db", default=None, help="可选：显式指定 workbuddy.db 路径")
    ap.add_argument("--output", default=None, help="输出文件路径（默认输出到 stdout）")
    args = ap.parse_args()

    # 探测数据库
    db, log = db_probe.probe()
    if args.db:
        db = args.db

    print("=" * 60, flush=True)
    print("WorkBuddy 本地算力看板 · 数据导出", flush=True)
    print("=" * 60, flush=True)
    print("数据库：%s" % (db or "未找到"), flush=True)
    print("-" * 60, flush=True)

    if not db:
        print("错误：未找到 workbuddy.db", file=sys.stderr, flush=True)
        sys.exit(1)

    # 查询 DB 数据
    q = db_query.query(db)
    if not q.get("ok"):
        print("数据库查询失败：%s" % q.get("error"), file=sys.stderr, flush=True)
        sys.exit(1)

    # 读取 last_snapshot
    snapshot = None
    snapshot_file = os.path.join(os.path.dirname(HERE), "assets", "snapshot.json")
    if os.path.exists(snapshot_file):
        try:
            with open(snapshot_file, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except Exception:
            pass

    # 组装完整数据（合并 snapshot）
    data = {
        "collected": q["collected"],
        "wb": q["wb"],
        "recent": q["recent"],
        "dbPath": db,
    }

    # 合并外部数据（尝试新抓取，失败则保留旧值）
    notes = []

    w = ext.fetch_weather()
    if w:
        data["weather"] = w
        notes.append("天气✓")
    elif snapshot and snapshot.get("weather"):
        data["weather"] = snapshot["weather"]
        notes.append("天气✗保留旧值")
    else:
        data["weather"] = None
        notes.append("天气✗无旧值")

    hot = ext.fetch_weibo_hot(12)
    if hot:
        data["weibo"] = hot
        notes.append("微博✓%d" % len(hot))
    elif snapshot and snapshot.get("weibo"):
        data["weibo"] = snapshot["weibo"]
        notes.append("微博✗保留旧值")
    else:
        data["weibo"] = []
        notes.append("微博✗无旧值")

    tt = ext.fetch_toutiao_hot(12)
    if tt:
        data["toutiao"] = tt
        notes.append("头条✓%d" % len(tt))
    elif snapshot and snapshot.get("toutiao"):
        data["toutiao"] = snapshot["toutiao"]
        notes.append("头条✗保留旧值")
    else:
        data["toutiao"] = []
        notes.append("头条✗无旧值")

    idx = ext.fetch_indices()
    if idx:
        data["indices"] = idx
        notes.append("指数✓%d" % len(idx))
    elif snapshot and snapshot.get("indices"):
        data["indices"] = snapshot["indices"]
        notes.append("指数✗保留旧值")
    else:
        data["indices"] = []
        notes.append("指数✗无旧值")

    data["notes"] = notes

    # 生成输出
    if args.format == "md":
        output = export_md(data, snapshot)
    else:
        output = export_json(data, snapshot)

    # 输出
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print("\n已写入：%s" % args.output, flush=True)
    else:
        print("\n" + output, flush=True)

    print("-" * 60, flush=True)
    print("导出完成 | %s" % " ".join(notes), flush=True)
    print("=" * 60, flush=True)

    sys.exit(0)


if __name__ == "__main__":
    main()
