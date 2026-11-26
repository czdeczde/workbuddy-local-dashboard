# -*- coding: utf-8 -*-
"""
只读查询 workbuddy.db，返回看板真实指标。
- DB 路径由 db_probe 自动探测，不写死。
- 表/字段结构随版本变化时，用信息架构探测 + 容错，缺字段给安全默认值，绝不编造数据。
- 只用标准库 sqlite3。
"""
import datetime
import json
import sqlite3

import db_probe


def _table_columns(cur, table):
    try:
        return {r[1] for r in cur.execute("PRAGMA table_info(%s)" % table)}
    except Exception:
        return set()


def _has_table(cur, table):
    try:
        r = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return bool(r)
    except Exception:
        return False


def _norm_status(s):
    s = (s or "").lower()
    if s == "completed":
        return "completed"
    if s in ("archived",):
        return "archived"
    if s in ("error", "failed"):
        return "failed"
    if s in ("terminated",):
        return "terminated"
    if s == "working":
        return "working"
    return s or "unknown"


def _safe_count(cur, sql, params=()):
    try:
        return cur.execute(sql, params).fetchone()[0] or 0
    except Exception:
        return 0


def query(db_path=None):
    """返回 dict：ok / collected / wb / recent / error。"""
    if not db_path:
        db_path, _ = db_probe.probe()
    if not db_path:
        return {"ok": False, "error": "未在本机探测到 workbuddy.db，可设置环境变量 WORKBUDDY_DB 指定路径"}

    con = None
    try:
        con = sqlite3.connect("file:" + db_path + "?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        now = datetime.datetime.now()
        today0 = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        has_sessions = _has_table(cur, "sessions")
        has_usage = _has_table(cur, "session_usage")

        sc = _table_columns(cur, "sessions")
        uc = _table_columns(cur, "session_usage")

        # 今日会话数
        sessions_today = 0
        if has_sessions and "created_at" in sc:
            sessions_today = _safe_count(
                cur, "SELECT COUNT(*) FROM sessions WHERE created_at>=?", (today0,))

        # 上下文占用（最新 session_usage）
        ctx_used, ctx_size = 0, 0
        if has_usage and "used" in uc:
            order = "ORDER BY updated_at DESC" if "updated_at" in uc else "ORDER BY rowid DESC"
            try:
                row = cur.execute("SELECT used,size FROM session_usage %s LIMIT 1" % order).fetchone()
                if row:
                    ctx_used = row["used"] or 0
                    ctx_size = (row["size"] or 0) if "size" in uc else 300000
            except Exception:
                pass
        if not ctx_size:
            ctx_size = 300000

        # 积分消耗 + token + 记录数
        credit_total, credit_records, token_total, session_records = 0.0, 0, 0, 0
        if has_usage:
            if "credit_json" in uc:
                for (cj,) in cur.execute(
                        "SELECT credit_json FROM session_usage WHERE credit_json IS NOT NULL"):
                    try:
                        d = json.loads(cj)
                        if isinstance(d, dict):
                            credit_total += sum(v for v in d.values()
                                                if isinstance(v, (int, float)))
                            credit_records += 1
                    except Exception:
                        pass
            if "used" in uc:
                token_total = _safe_count(cur, "SELECT SUM(used) FROM session_usage")
            session_records = _safe_count(cur, "SELECT COUNT(*) FROM session_usage")

        # 状态分布
        counts, total_sessions = {}, 0
        if has_sessions and "status" in sc:
            where = "WHERE deleted_at IS NULL" if "deleted_at" in sc else ""
            for r in cur.execute(
                    "SELECT status,COUNT(*) n FROM sessions %s GROUP BY status" % where):
                k = _norm_status(r["status"])
                counts[k] = counts.get(k, 0) + r["n"]
                total_sessions += r["n"]

        # 当前会话与模型
        state, model = "在线 · 未探测到运行中会话", "-"
        if has_sessions and "status" in sc:
            where = "WHERE deleted_at IS NULL" if "deleted_at" in sc else ""
            andw = "AND" if where else "WHERE"
            ordcol = "last_activity_at" if "last_activity_at" in sc else "rowid"
            sel_model = "model" if "model" in sc else "NULL"
            try:
                live = cur.execute(
                    "SELECT title,%s AS model FROM sessions %s %s lower(status)='working' "
                    "ORDER BY %s DESC LIMIT 1" % (sel_model, where, andw, ordcol)
                ).fetchone()
                if live:
                    state = "在线 · 当前会话运行中"
                    model = live["model"] or "-"
            except Exception:
                pass

        # 最近会话
        recent = []
        if has_sessions:
            cols = ["title" if "title" in sc else "NULL AS title",
                    "status" if "status" in sc else "NULL AS status",
                    "last_activity_at" if "last_activity_at" in sc else "0 AS last_activity_at",
                    "is_background_automation" if "is_background_automation" in sc else "0 AS is_background_automation"]
            where = "WHERE deleted_at IS NULL" if "deleted_at" in sc else ""
            ordcol = "last_activity_at" if "last_activity_at" in sc else "rowid"
            try:
                for r in cur.execute(
                        "SELECT %s FROM sessions %s ORDER BY %s DESC LIMIT 11"
                        % (",".join(cols), where, ordcol)):
                    st = str(r["status"]).lower()
                    recent.append({
                        "nm": r["title"] or "(无标题会话)",
                        "ts": r["last_activity_at"] or 0,
                        "bg": bool(r["is_background_automation"]),
                        "live": st == "working",
                    })
            except Exception:
                pass

        return {
            "ok": True,
            "collected": now.strftime("%Y-%m-%d %H:%M:%S"),
            "dbPath": db_path,
            "wb": {
                "sessionsToday": sessions_today,
                "ctxUsed": ctx_used, "ctxSize": ctx_size,
                "creditTotal": round(credit_total, 2), "creditRecords": credit_records,
                "tokenTotal": token_total, "sessionRecords": session_records,
                "statusCounts": counts, "totalSessions": total_sessions,
                "state": state, "model": model,
            },
            "recent": recent,
        }
    except Exception as e:
        return {"ok": False, "error": "读取数据库失败：%s" % e}
    finally:
        if con:
            try:
                con.close()
            except Exception:
                pass


if __name__ == "__main__":
    import json as _json
    p, log = db_probe.probe()
    print("== 探测日志 ==\n%s" % log)
    print("\n== 查询结果 ==")
    print(_json.dumps(query(p), ensure_ascii=False, indent=2))
