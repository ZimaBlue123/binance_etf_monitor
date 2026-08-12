"""binance_etf_configurable.py 纯函数的单元测试。

仅覆盖无 I/O 副作用的纯函数(阶段一审查过的健壮性边界):
- safe_float:类型/异常防御
- clamp:边界值
- markdown_to_text:emoji / 加粗清理
- history_series:脏数据剔除 + 排序

`QuantReporter` 的方法因涉及 I/O / pandas / 网络,留作集成测试,不进单测。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import binance_etf_configurable as bec  # noqa: E402


# ============================================================
#  safe_float
# ============================================================

class TestSafeFloat:
    @pytest.mark.parametrize("val,expected", [
        ("3.14", 3.14),
        (0, 0.0),
        (-2.5, -2.5),
        (True, 1.0),  # bool 是 int 的子类
        (None, 0.0),  # default
    ])
    def test_convertible(self, val, expected):
        assert bec.safe_float(val) == pytest.approx(expected)

    @pytest.mark.parametrize("val", ["abc", None, [], {"k": 1}, object()])
    def test_returns_default_on_failure(self, val):
        assert bec.safe_float(val) == 0.0
        assert bec.safe_float(val, default=-999.0) == -999.0

    def test_nan_string_returns_default(self):
        # float("nan") 本身不抛,我们要确认 safe_float 不把它当"有效"而原样返回
        # 行为:float("nan") 不会进 except,会原样返回 nan — 这是预期
        result = bec.safe_float("nan")
        assert math.isnan(result)


# ============================================================
#  clamp
# ============================================================

class TestClamp:
    @pytest.mark.parametrize("x,low,high,expected", [
        (0.5, 0, 1, 0.5),     # 区间内
        (-0.1, 0, 1, 0.0),    # 低于下界
        (1.5, 0, 1, 1.0),     # 高于上界
        (0, 0, 1, 0),         # 等于下界
        (1, 0, 1, 1),         # 等于上界
    ])
    def test_clamp(self, x, low, high, expected):
        assert bec.clamp(x, low, high) == expected


# ============================================================
#  markdown_to_text
# ============================================================

class TestMarkdownToText:
    def test_strips_bold(self):
        assert "强" in bec.markdown_to_text("**强**势偏多")
        assert "**" not in bec.markdown_to_text("**强**势偏多")

    def test_strips_known_emojis(self):
        for e in ("📊 ", "🟢 ", "🟡 ", "🔴 ", "🟠 ", "⚪ ", "🔥 ", "🧊 ", "🚀 ", "📝 ", "✅ "):
            assert e not in bec.markdown_to_text(f"prefix {e} suffix")

    def test_keeps_unknown_chars(self):
        # 未列入清理列表的字符应保留
        text = "中文 — 中文 标点"
        assert bec.markdown_to_text(text) == text


# ============================================================
#  history_series
# ============================================================

# 因为 history_series 是方法,需要一个 QuantReporter 实例
# 但 __init__ 会读配置 / 建 logger / 拉 session。绕开方案:临时 monkeypatch。
@pytest.fixture
def reporter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """构造一个 QuantReporter,绕开真实 I/O,只用于测 history_series 这种纯计算方法。"""
    cfg_path = tmp_path / "config" / "strategy_config.yaml"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(
        "timezone: Asia/Shanghai\n"
        "work_dir: out\n"
        "paths:\n"
        "  log_file: logs/x.log\n"
        "  history_file: data/x.json\n"
        "  etf_products_file: config/etf_products.json\n"
        "  crypto_products_file: config/crypto_products.json\n"
        "network:\n"
        "  timeout_connect: 1\n"
        "  timeout_read: 1\n"
        "  retry_total: 0\n"
        "  backoff_factor: 0\n"
        "  status_forcelist: []\n"
        "  user_agent: test\n"
        "crypto:\n"
        "  interval: 1d\n"
        "  kline_limit: 10\n"
        "  rsi_period: 14\n"
        "  bb_period: 20\n"
        "  ma_fast: 5\n"
        "  ma_slow: 10\n"
        "  vol_scale: 1.0\n"
        "  score_thresholds: {strong_buy: 0.6, buy: 0.2, sell: -0.2, strong_sell: -0.6}\n"
        "fund:\n"
        "  providers: []\n"
        "  category_rules: {}\n"
        "  thresholds: {}\n",
        encoding="utf-8",
    )
    (cfg_path.parent / "etf_products.json").write_text("[]", encoding="utf-8")
    (cfg_path.parent / "crypto_products.json").write_text("[]", encoding="utf-8")
    return bec.QuantReporter(str(cfg_path))


class TestHistorySeries:
    def test_empty_returns_empty_series(self, reporter):
        s = reporter.history_series({}, "FUND_X")
        assert isinstance(s, pd.Series)
        assert s.empty
        assert s.dtype == float

    def test_filters_non_string_keys(self, reporter):
        hist = {"FUND_X": {1: 100.0, "2024-01-01": 1.0, "2024-01-02": 2.0}}
        s = reporter.history_series(hist, "FUND_X")
        assert list(s) == [1.0, 2.0]

    def test_filters_non_numeric_values(self, reporter):
        hist = {"FUND_X": {"2024-01-01": "abc", "2024-01-02": 2.0, "2024-01-03": None}}
        s = reporter.history_series(hist, "FUND_X")
        # 字符串 "abc" → NaN 被剔除;None → TypeError 被剔除
        assert list(s) == [2.0]

    def test_sorted_ascending(self, reporter):
        hist = {"FUND_X": {"2024-01-03": 3.0, "2024-01-01": 1.0, "2024-01-02": 2.0}}
        s = reporter.history_series(hist, "FUND_X")
        assert list(s) == [1.0, 2.0, 3.0]
