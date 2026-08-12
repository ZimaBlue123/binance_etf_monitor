#!/data/data/com.termux/files/usr/bin/bash
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
python scripts/validate_strategy_assets.py "$@"
