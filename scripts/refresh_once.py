# -*- coding: utf-8 -*-
"""
WorkBuddy 本地算力看板 · 单次刷新（合并 last_snapshot）
用法：python refresh_once.py [--db 路径] [--timeout 60]
功能：
  - 调用 dashboard.refresh() 执行完整合并逻辑
  - 总超时控制（默认 60 秒），超时后返回部分结果
  - 输出标准化结果（exit code + 标准输出 + 标准错误）
  - 更新 assets/snapshot.json 作为新的 last_snapshot
"""
import argparse
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import dashboard


def main():
    ap = argparse.ArgumentParser(description="WorkBuddy 本地算力看板 · 单次刷新")
    ap.add_argument("--db", default=None, help="可选：显式指定 workbuddy.db 路径")
    ap.add_argument("--timeout", type=int, default=60, help="总超时秒数（默认 60）")
    ap.add_argument("--output", default=None, help="输出文件路径（默认输出到 stdout）")
    args = ap.parse_args()

    # 设置数据库路径
    db, log = dashboard.db_probe.probe()
    if args.db:
        db = args.db
    dashboard._state["db"] = db
    dashboard._state["db_source"] = "显式指定" if args.db else ("自动探测" if db else "未找到")

    print("=" * 60, flush=True)
    print("WorkBuddy 本地算力看板 · 单次刷新", flush=True)
    print("=" * 60, flush=True)
    print("数据库：%s (%s)" % (db or "未找到", dashboard._state["db_source"]), flush=True)
    print("超时：%d 秒" % args.timeout, flush=True)
    print("-" * 60, flush=True)

    # 使用线程实现超时控制
    result = {"ok": False, "data": None, "error": None}
    exception = [None]

    def _refresh():
        try:
            ok, data = dashboard.refresh()
            result["ok"] = ok
            result["data"] = data
            result["error"] = None
        except Exception as e:
            result["ok"] = False
            result["data"] = None
            result["error"] = str(e)
            exception[0] = e

    thread = threading.Thread(target=_refresh)
    thread.daemon = True
    thread.start()
    thread.join(timeout=args.timeout)

    if thread.is_alive():
        # 超时
        print("\n[超时] 刷新操作超过 %d 秒，返回部分结果" % args.timeout, file=sys.stderr, flush=True)
        # 尝试返回已有状态
        if dashboard._state.get("data"):
            result["ok"] = True
            result["data"] = dashboard._state["data"]
            result["error"] = None
        else:
            result["ok"] = False
            result["error"] = "超时且无旧数据可用"
    elif result["error"]:
        print("\n[失败] %s" % result["error"], file=sys.stderr, flush=True)
    else:
        print("\n[成功] 刷新完成", flush=True)

    # 输出结果
    output_data = {
        "ok": result["ok"],
        "collected": result["data"].get("collected") if result["data"] else None,
        "notes": result["data"].get("notes") if result["data"] else [],
        "error": result["error"],
    }

    output_json = json.dumps(output_data, ensure_ascii=False, indent=2)

    if args.output:
        # 写入文件
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print("\n已写入：%s" % args.output, flush=True)
    else:
        # 输出到 stdout
        print("\n" + output_json, flush=True)

    # 打印摘要
    print("-" * 60, flush=True)
    if result["ok"]:
        wb = result["data"].get("wb", {})
        print("摘要:", flush=True)
        print("  今日会话=%s 上下文=%s/%s 积分=%s Token=%s" % (
            wb.get("sessionsToday", 0),
            wb.get("ctxUsed", 0),
            wb.get("ctxSize", 0),
            wb.get("creditTotal", 0),
            wb.get("tokenTotal", 0),
        ), flush=True)
        if result["data"].get("indices"):
            print("  指数=" + " ".join(
                "%s %s(%+.2f%%)" % (x["name"], x["price"], x["pct"])
                for x in result["data"]["indices"]
            ), flush=True)
        # 标注保留旧值的数据源
        notes = result["data"].get("notes", [])
        stale_notes = [n for n in notes if "✗" in n or "保留旧值" in n]
        if stale_notes:
            print("\n保留旧值的数据源:", flush=True)
            for note in stale_notes:
                print("  - %s" % note, flush=True)
    else:
        print("刷新失败，请检查数据库路径或网络连接", flush=True)

    print("=" * 60, flush=True)

    # 返回退出码
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
