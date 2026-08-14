@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [*] 检查 Python 环境...
set "PY_CMD="
for %%C in ("py -3" "python" "python3") do (
    if not defined PY_CMD (
        %%~C -c "import yaml" >nul 2>&1
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
echo [*] 正在运行策略资产校验...
%PY_CMD% "scripts\validate_strategy_assets.py"
if errorlevel 1 (
    echo [!] 校验未通过 (退出码: %errorlevel%)
    pause
    exit /b %errorlevel%
)

echo [*] 校验通过。
pause
