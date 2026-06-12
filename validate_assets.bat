@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "scripts\validate_strategy_assets.py"
pause
