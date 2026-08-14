@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [*] 检查 Python 环境...
set "PY_CMD="
for %%C in ("py -3" "python" "python3") do (
    if not defined PY_CMD (
        %%~C -c "import yaml, requests, pandas" >nul 2>&1
        if not errorlevel 1 set "PY_CMD=%%~C"
    )
)

if not defined PY_CMD (
    for %%C in ("py -3" "python" "python3") do (
        if not defined PY_CMD (
            %%~C --version >nul 2>&1
            if not errorlevel 1 set "PY_CMD=%%~C"
        )
    )
)

if not defined PY_CMD (
    echo [!] 错误: 未找到可用的 Python 环境。请确认 Python 已安装并添加到 PATH。
    pause
    exit /b 1
)

echo [*] 使用 Python: %PY_CMD%
echo [*] 正在运行 Binance ETF 监控...
%PY_CMD% "binance_etf_configurable.py"
if errorlevel 1 (
    echo [!] 程序异常退出 (退出码: %errorlevel%)
    pause
    exit /b %errorlevel%
)

echo [*] 完成。
pause
