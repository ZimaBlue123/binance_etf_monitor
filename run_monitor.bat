@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "binance_etf_configurable.py"
pause
