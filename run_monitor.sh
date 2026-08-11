#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检测可用的 Python 解释器（优先 python3，回退 python）
PYTHON_BIN=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON_BIN="$cmd"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[!] 错误: 未找到 Python 解释器 (python3 / python)。" >&2
    exit 1
fi

echo "[*] 使用 Python: $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"
echo "[*] 正在运行 Binance ETF 监控..."
"$PYTHON_BIN" "binance_etf_configurable.py"
