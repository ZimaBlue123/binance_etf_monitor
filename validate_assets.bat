@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "scriptsvalidate_strategy_assets.py"
pause
