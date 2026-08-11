@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [*] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] 错误: 未找到 Python。请确认 Python 已安装并添加到 PATH。
    echo     或者修改本脚本中的 python 为完整路径。
    pause
    exit /b 1
)

echo [*] 正在运行 Binance ETF 监控...
python "binance_etf_configurable.py"
if errorlevel 1 (
    echo [!] 程序异常退出 (退出码: %errorlevel%)
    pause
    exit /b %errorlevel%
)

echo [*] 完成。
pause
