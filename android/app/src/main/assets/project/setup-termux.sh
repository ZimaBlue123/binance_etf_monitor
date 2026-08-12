#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
#  Binance ETF Monitor — Termux 一键初始化
#  用法 (在 Termux 内执行):
#     bash setup-termux.sh
#  说明:
#     1. 安装 Python 及 pip
#     2. 把 APK 内嵌的 /assets/project 内容拷贝到 ~/binance_etf_monitor/
#     3. 建立 venv 并安装 requirements.txt
#     4. 注册 ~/bin/run_monitor.sh 快捷命令
# =============================================================================
set -euo pipefail

PROJ_DIR="$HOME/binance_etf_monitor"
ASSETS_DIR="/data/data/com.Mavis.binanceetfmonitor/files/project"

echo "==> [1/5] 更新 pkg + 装 python / clang / libffi"
pkg update -y
pkg install -y python clang libffi openssl libcrypt

echo "==> [2/5] 准备项目目录: $PROJ_DIR"
mkdir -p "$PROJ_DIR"
# 从 APK 的 assets 解出来的项目根目录拷过去
if [ -d "$ASSETS_DIR" ]; then
    cp -r "$ASSETS_DIR"/. "$PROJ_DIR"/
else
    echo "WARNING: APK assets/project 不存在, 请确认你从本项目生成的 APK 安装"
fi

cd "$PROJ_DIR"
chmod +x run_monitor.sh validate_assets.sh 2>/dev/null || true

echo "==> [3/5] 创建 venv 并装依赖"
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> [4/5] 跑一次自检 (不阻塞初始化)"
python scripts/validate_strategy_assets.py || echo "WARN: 自检有 warning, 不影响运行"

echo "==> [5/5] 注册快捷命令 ~/bin/run_monitor.sh"
mkdir -p "$HOME/bin"
cat > "$HOME/bin/run_monitor.sh" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
set -e
cd "$HOME/binance_etf_monitor"
source .venv/bin/activate
export TZ="Asia/Shanghai"
python binance_etf_configurable.py "$@"
EOF
chmod +x "$HOME/bin/run_monitor.sh"

echo
echo "============================================================"
echo " 初始化完成!"
echo " 启动监控:  run_monitor.sh"
echo " 报告目录:  $PROJ_DIR/output/reports/"
echo "============================================================"
echo
echo ">>> 可选: 注册每日 06:00 自动跑监控"
echo "    方法 A (推荐) — Termux:Tasker (Play/F-Droid 都有):"
echo "        Task 配置: Time 06:00 →  Run Termux command:"
echo "        bash $PROJ_DIR/run_monitor.sh"
echo
echo "    方法 B — Termux 自带 crond (省心但要 root 模拟层):"
echo "        pkg install -y termux-services cronie"
echo "        sv-enable crond && sv up crond"
echo "        (crontab -l ; echo '0 6 * * * bash $PROJ_DIR/run_monitor.sh >>$PROJ_DIR/output/cron.log 2>&1') | crontab -"
echo
echo "    方法 C — 唤醒锁+循环 (最暴力, 不推荐):"
echo "        termux-wake-lock; while sleep 86400; do bash $PROJ_DIR/run_monitor.sh; done"
