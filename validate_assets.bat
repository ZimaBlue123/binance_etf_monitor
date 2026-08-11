@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [*] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] 错误: 未找到 Python。请确认 Python 已安装并添加到 PATH。
    pause
    exit /b 1
)

echo [*] 正在运行策略资产校验...
python "scripts\validate_strategy_assets.py"
if errorlevel 1 (
    echo [!] 校验未通过 (退出码: %errorlevel%)
    pause
    exit /b %errorlevel%
)

echo [*] 校验通过。
pause
