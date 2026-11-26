# -*- coding: utf-8 -*-
"""
WorkBuddy 本地算力看板 · 一键服务（免费版 / 纯本机 / 无 NAS）
用法：python dashboard.py [--port 8901] [--host 127.0.0.1]
功能：
  - 自动探测本机 workbuddy.db（见 db_probe.py），不写死路径
  - 每 30 分钟自动刷新一次快照（后台线程），页面每 30 秒检查数据是否变化并自动重载
  - 外部数据（天气/热搜/热榜/指数）失败自动保留上次值，绝不编造
  - 只监听 127.0.0.1，数据不出本机
  - 自动探测 python/python3 可执行文件，适配不同运行环境
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ===== Python 可执行文件自动探测 =====
def _find_python():
    """返回可用的 python 解释器路径(优先当前进程,其次 PATH 中的 python/python3)。"""
    candidates = [sys.executable]
    for name in ("python", "python3"):
        try:
            p = subprocess.check_output(
                ["where" if os.name == "nt" else "which", name],
                stderr=subprocess.DEVNULL, text=True
            ).strip()
            if p and os.path.isfile(p):
                candidates.append(p)
        except Exception:
            pass
    # 去重并保持顺序
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[0] if out else sys.executable

PYTHON_BIN = _find_python()

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
sys.path.insert(0, HERE)

import db_probe
import db_query
import fetch_external as ext

HTML_FILE = os.path.join(ASSETS, "dashboard.html")
CITY_FILE = os.path.join(HERE, "weather_city.json")
SNAPSHOT_FILE = os.path.join(ASSETS, "snapshot.json")
DATA_RE = re.compile(r"const DATA = (\{[\s\S]*?\n\});")
REFRESH_SEC = 30 * 60  # 每 30 分钟刷新

_state = {"data": None, "last": 0, "db": None, "db_source": "", "lock": threading.Lock()}


def _read_existing(html):
    m = DATA_RE.search(html)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def build_payload(q, old):
    """组装与看板 HTML 兼容的 DATA 对象。"""
    wb = q["wb"]
    old_wb = (old or {}).get("wb") or {}
    weather = old.get("weather") if old else None
    weibo = (old or {}).get("weibo", [])
    toutiao = (old or {}).get("toutiao", [])
    indices = (old or {}).get("indices", [])

    notes = []
    w = ext.fetch_weather()
    if w:
        weather = w
        notes.append("天气✓")
    else:
        notes.append("天气✗保留旧值")

    hot = ext.fetch_weibo_hot(12)
    if hot:
        weibo = hot
        notes.append("微博✓%d" % len(hot))
    else:
        notes.append("微博✗保留旧值")

    tt = ext.fetch_toutiao_hot(12)
    if tt:
        toutiao = tt
        notes.append("头条✓%d" % len(tt))
    else:
        notes.append("头条✗保留旧值")

    idx = ext.fetch_indices()
    if idx:
        indices = idx
        notes.append("指数✓%d" % len(idx))
    else:
        notes.append("指数✗保留旧值")

    data = {
        "collected": q["collected"],
        "wb": {
            "sessionsToday": wb["sessionsToday"],
            "ctxUsed": wb["ctxUsed"], "ctxSize": wb["ctxSize"],
            "creditTotal": wb["creditTotal"], "creditRecords": wb["creditRecords"],
            "tokenTotal": wb["tokenTotal"], "sessionRecords": wb["sessionRecords"],
            "statusCounts": wb["statusCounts"], "totalSessions": wb["totalSessions"],
            "state": wb["state"], "model": wb["model"],
            "creditBalance": None,  # DB 无余额字段
        },
        "recent": q["recent"],
        "weather": weather or {},
        "indices": indices,
        "weibo": weibo,
        "toutiao": toutiao,
        "life": (old or {}).get("life", {"birth": "1980-11-05", "total": 30000}),
        "dbPath": q.get("dbPath", ""),
        "dbSource": _state.get("db_source", ""),
        "refreshSec": REFRESH_SEC,
        "notes": notes,
    }
    return data


def refresh():
    """拉真实数据 + 回写 HTML 的 const DATA 块。返回 (ok, data_or_error)。"""
    with _state["lock"]:
        q = db_query.query(_state.get("db"))
        if not q.get("ok"):
            return False, q.get("error", "本地库查询失败")
        try:
            with open(HTML_FILE, "r", encoding="utf-8") as f:
                html = f.read()
            old = _read_existing(html)
            data = build_payload(q, old)
            js = json.dumps(data, ensure_ascii=False, indent=2)
            # 用 lambda 做替换，避免 re.sub 把 JSON 里的 \\ 当反向引用二次解析
            new_html, n = DATA_RE.subn(lambda m: "const DATA = " + js + ";", html, count=1)
            if n != 1:
                # 模板尚无 DATA 块时，追加到 </script> 前
                marker = "</body>"
                if marker in new_html:
                    new_html = new_html.replace(
                        marker, "<script>\nconst DATA = " + js + ";\n</script>\n" + marker, 1)
                else:
                    return False, "未找到 const DATA 块且无法插入"
            tmp = HTML_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(new_html)
            os.replace(tmp, HTML_FILE)
            # 同时更新 last_snapshot 文件
            _save_snapshot(data)
            _state["data"] = data
            _state["last"] = time.time()
            return True, data
        except Exception as e:
            return False, "回写失败：%s" % e


def _save_snapshot(data):
    """保存 last_snapshot 文件，供后续合并使用。"""
    try:
        tmp = SNAPSHOT_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SNAPSHOT_FILE)
    except Exception:
        pass  # 快照保存失败不影响主流程


def _auto_refresh_loop():
    while True:
        time.sleep(REFRESH_SEC)
        try:
            ok, r = refresh()
            print("[%s] 自动刷新 %s" % (
                datetime.datetime.now().strftime("%H:%M:%S"),
                "OK" if ok else "FAIL: " + str(r)))
        except Exception as e:
            print("[%s] 自动刷新异常：%s" % (
                datetime.datetime.now().strftime("%H:%M:%S"), e))


class Handler(BaseHTTPRequestHandler):
    server_version = "WBLocalBoard/1.0"

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/data":
            d = _state.get("data")
            if not d:
                self._send(503, json.dumps({"ok": False, "error": "数据尚未就绪"}),
                           "application/json; charset=utf-8")
            else:
                self._send(200, json.dumps({
                    "ok": True, "collected": d["collected"], "last": _state["last"],
                    "data": d,
                }, ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/api/refresh":
            ok, r = refresh()
            if ok:
                self._send(200, json.dumps({
                    "ok": True, "collected": r["collected"], "data": r,
                }, ensure_ascii=False), "application/json; charset=utf-8")
            else:
                self._send(500, json.dumps({"ok": False, "error": str(r)},
                                           ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/api/weather":
            # 切换城市并返回新天气数据
            qs = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = urllib.parse.parse_qs(qs)
            city = params.get("city", [""])[0].strip()
            if not city:
                self._send(400, json.dumps({"ok": False, "error": "城市名不能为空"}, ensure_ascii=False),
                           "application/json; charset=utf-8")
                return
            try:
                import fetch_external as ext
                w = ext.fetch_weather(city=city)
                if not w:
                    self._send(500, json.dumps({"ok": False, "error": "获取天气失败"}, ensure_ascii=False),
                               "application/json; charset=utf-8")
                else:
                    self._send(200, json.dumps({"ok": True, "weather": w}, ensure_ascii=False),
                               "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
                           "application/json; charset=utf-8")
        elif path in ("/", "/index.html", "/dashboard.html"):
            try:
                with open(HTML_FILE, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except Exception as e:
                self._send(500, "看板文件读取失败：%s" % e, "text/plain; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def log_message(self, fmt, *args):
        print("[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), fmt % args))


def main():
    ap = argparse.ArgumentParser(description="WorkBuddy 本地算力看板（免费版）")
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="监听地址，默认仅本机 127.0.0.1；如需局域网访问显式传 --host 0.0.0.0")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8901)))
    ap.add_argument("--db", default=None, help="可选：显式指定 workbuddy.db 路径")
    args = ap.parse_args()

    db, log = db_probe.probe()
    if args.db:
        db = args.db
    _state["db"] = db
    _state["db_source"] = "显式指定" if args.db else ("自动探测" if db else "未找到")

    print("=" * 56)
    print("WorkBuddy 本地算力看板 · 免费版（纯本机 / 无 NAS）")
    print("=" * 56)
    print("数据库探测：")
    for line in log.splitlines():
        print("  " + line)
    print("  => 使用：%s (%s)" % (db or "未找到", _state["db_source"]))
    print("看板地址：http://%s:%d/" % (args.host, args.port))
    print("自动刷新：每 %d 分钟" % (REFRESH_SEC // 60))
    print("停止服务：Ctrl+C")
    print("=" * 56, flush=True)

    # 先起 HTTP 服务，再异步拉数据：避免外部接口慢时页面打不开
    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        print("启动失败（端口可能被占用）：%s" % e, file=sys.stderr)
        sys.exit(1)

    def _first_refresh():
        ok, r = refresh()
        if ok:
            print("[启动] 快照已更新 %s | %s" % (
                r["collected"], " ".join(r.get("notes", []))), flush=True)
        else:
            print("[启动] 刷新失败（显示上次快照）：%s" % r, file=sys.stderr, flush=True)

    threading.Thread(target=_first_refresh, daemon=True).start()
    threading.Thread(target=_auto_refresh_loop, daemon=True).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
