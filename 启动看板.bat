@echo off
chcp 65001 >nul
title WorkBuddy 本地算力看板（免费版）
cd /d "%~dp0"

echo ============================================
echo   WorkBuddy 本地算力看板 - 免费版
echo   纯本机运行 / 自动探测数据库 / 无 NAS
echo ============================================
echo.
echo   正在启动，请保持本窗口打开...
echo.

:: 自动探测空闲端口（8901–8910），避开已被占用的
set "PORT=8901"
for %%p in (8901 8902 8903 8904 8905 8906 8907 8908 8909 8910) do (
    netstat -an | findstr ":%%p " | findstr "LISTENING" >nul
    if errorlevel 1 (
        set "PORT=%%p"
        goto :port_found
    )
)
echo.
echo 无法找到空闲端口（8901-8910 均被占用），请关闭占用程序后重试。
pause
exit /b 1
:port_found

echo   使用端口: %PORT%
echo   看板地址: http://127.0.0.1:%PORT%/
echo   自动刷新: 每 30 分钟
echo   停止服务: 在本窗口按 Ctrl+C
echo.

start "" http://127.0.0.1:%PORT%/
python scripts\dashboard.py --port %PORT%

echo.
echo   服务已停止。
pause
