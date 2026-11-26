# -*- coding: utf-8 -*-
"""
自动探测本机 workbuddy.db 位置（不写死任何用户目录）。
探测顺序：
  1) 环境变量 WORKBUDDY_DB 显式指定
  2) 当前技能目录 / 当前工作目录 附近
  3) 用户主目录 ~/.workbuddy/ 下（跨平台）
  4) 递归扫描用户主目录 2 层内的 workbuddy.db（限制数量，避免全盘慢扫）
返回 (路径, 来源说明) 或 (None, 探测日志)。
"""
import os
import sys

DB_NAME = "workbuddy.db"


def _candidates():
    out = []

    # 1) 显式环境变量
    env = os.environ.get("WORKBUDDY_DB")
    if env:
        out.append((env, "环境变量 WORKBUDDY_DB"))

    home = os.path.expanduser("~")

    # 2) 技能目录及其父级
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (here, os.path.dirname(here), os.path.dirname(os.path.dirname(here))):
        out.append((os.path.join(d, DB_NAME), "技能目录附近"))

    # 3) 标准 ~/.workbuddy/
    out.append((os.path.join(home, ".workbuddy", DB_NAME), "用户主目录 ~/.workbuddy"))

    # Windows 常见位置
    if os.name == "nt":
        for base in ("APPDATA", "LOCALAPPDATA"):
            root = os.environ.get(base)
            if root:
                out.append((os.path.join(root, "workbuddy", DB_NAME), "%s/workbuddy" % base))
        # 用户目录下常见安装名
        for sub in ("WorkBuddy", "workbuddy数据", ".workbuddy"):
            out.append((os.path.join(home, sub, DB_NAME), "用户目录/%s" % sub))

    # 4) 受控递归：只在 home 下扫 2 层，最多 200 个目录，避免卡死
    seen = set()
    scanned = 0
    for root, dirs, files in os.walk(home):
        # 跳过隐藏/系统大目录
        dirs[:] = [d for d in dirs if not d.startswith((".git", "node_modules", "AppData",
                                                        "__pycache__", "site-packages"))]
        scanned += 1
        if scanned > 200:
            break
        if DB_NAME in files:
            p = os.path.join(root, DB_NAME)
            if p not in seen:
                seen.add(p)
                out.append((p, "自动扫描用户目录"))
        if root.count(os.sep) - home.count(os.sep) >= 2:
            dirs[:] = []
    return out


def probe():
    """返回 (db_path 或 None, 日志字符串)。"""
    logs = []
    tried = set()
    for path, source in _candidates():
        path = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
        if path in tried:
            continue
        tried.add(path)
        if os.path.isfile(path):
            logs.append("HIT  [%s] %s" % (source, path))
            return path, "\n".join(logs)
        logs.append("miss [%s] %s" % (source, path))
    return None, "\n".join(logs)


if __name__ == "__main__":
    p, log = probe()
    print(log)
    print("RESULT:", p if p else "NOT FOUND")
    sys.exit(0 if p else 1)
