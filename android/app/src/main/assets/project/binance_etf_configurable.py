#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance ETF Monitor — 日度策略监控主程序

配置驱动，拉取加密资产与基金行情数据，生成日度策略观察报告。
"""

from __future__ import annotations

import os
import sys
import json
import math
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry
import yaml

__all__ = ["QuantReporter", "main"]

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "strategy_config.yaml"


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


configure_console_encoding()


def load_config(path: str | Path) -> dict[str, Any]:
    """读取配置文件并返回字典，支持 YAML / JSON 格式。"""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"配置文件不存在或不是常规文件: {path}")
    if p.suffix.lower() in [".yaml", ".yml"]:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"YAML 配置文件解析失败: {path} | {e}") from e
        if not isinstance(data, dict):
            raise ValueError(f"配置文件内容无效（期望 dict，实际 {type(data).__name__}）: {path}")
        return data
    if p.suffix.lower() == ".json":
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 配置文件解析失败: {path} | {e}") from e
        if not isinstance(data, dict):
            raise ValueError(f"配置文件内容无效（期望 dict，实际 {type(data).__name__}）: {path}")
        return data
    raise ValueError(f"仅支持 .yaml/.yml/.json 配置文件: {path}")


def load_json(path: str | Path) -> Any:
    """读取 JSON 资产清单文件，显式抛错便于上层定位。"""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"资产清单不存在或不是常规文件: {path}")
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"资产清单 JSON 解析失败: {path} | {e}") from e


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def clamp(x: float, low: float, high: float) -> float:
    if low > high:
        low, high = high, low
    return max(low, min(high, x))


def markdown_to_text(content: str) -> str:
    """将 Markdown 报告转为纯文本：去除加粗标记与 emoji 前缀。"""
    if not isinstance(content, str):
        return ""
    text = content.replace("**", "").replace("***", "")
    for emoji in ("📊 ", "🟢 ", "🟡 ", "🔴 ", "🟠 ", "⚪ ", "🔥 ", "🧊 ", "🚀 ", "📝 ", "✅ "):
        text = text.replace(emoji, "")
    return text


class QuantReporter:
    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path).expanduser().resolve()
        self._pending_debug_logs: list[str] = []
        self._setup_paths()
        self._setup_timezone()
        self._setup_logger()
        self.session = self._build_session()
        self._load_asset_lists()
        self.max_neutral_funds_in_report = int(
            self.cfg.get("fund", {}).get("report", {}).get("max_neutral_items", 20)
        )

    def _setup_paths(self) -> None:
        parent_name = self.config_path.parent.name
        base = self.config_path.parent
        self.project_dir = base.parent if parent_name == "config" else base
        self.cfg = load_config(self.config_path)

        if "work_dir" not in self.cfg or not self.cfg["work_dir"]:
            raise ValueError(f"配置缺少必要字段 'work_dir': {self.config_path}")
        self.work_dir = self._resolve_path(self.cfg["work_dir"])
        self.work_dir.mkdir(parents=True, exist_ok=True)

        paths = self.cfg.get("paths")
        if not isinstance(paths, dict):
            raise ValueError(f"配置缺少或无效的 'paths' 字段: {self.config_path}")
        for req_path_key in ("log_file", "history_file", "etf_products_file", "crypto_products_file"):
            if req_path_key not in paths:
                raise ValueError(f"配置 paths 缺少必要字段 '{req_path_key}': {self.config_path}")

        self.log_file = self.work_dir / paths["log_file"]
        self.history_file = self.work_dir / paths["history_file"]
        self.etf_file = self._resolve_path(paths["etf_products_file"])
        self.crypto_file = self._resolve_path(paths["crypto_products_file"])

    def _setup_timezone(self) -> None:
        os.environ["TZ"] = str(self.cfg.get("timezone", "Asia/Shanghai"))
        try:
            time.tzset()
        except (AttributeError, OSError):
            self._pending_debug_logs.append(
                f"time.tzset() 不可用,使用环境默认时区 TZ={os.environ.get('TZ', '<unset>')}"
            )

    def _setup_logger(self) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("binance_etf_monitor")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            try:
                fh = logging.FileHandler(self.log_file, encoding="utf-8")
                fh.setFormatter(formatter)
                self.logger.addHandler(fh)
            except OSError as e:
                print(f"[!] 无法初始化文件日志记录器: {e}", file=sys.stderr)
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(formatter)
            self.logger.addHandler(sh)

        for msg in self._pending_debug_logs:
            self.logger.debug(msg)
        self._pending_debug_logs.clear()

    def _load_asset_lists(self) -> None:
        try:
            self.crypto_products = load_json(self.crypto_file)
        except (FileNotFoundError, ValueError) as e:
            self.logger.error(f"[!] 加密资产清单加载失败: {e}")
            raise
        try:
            self.etf_products = load_json(self.etf_file)
        except (FileNotFoundError, ValueError) as e:
            self.logger.error(f"[!] ETF 资产清单加载失败: {e}")
            raise

    def _resolve_path(self, raw_path: str | Path) -> Path:
        p = Path(raw_path).expanduser()
        if p.is_absolute():
            return p
        return (self.project_dir / p).resolve()

    def _build_session(self) -> requests.Session:
        ncfg = self.cfg.get("network", {})
        retry_total = int(ncfg.get("retry_total", 3))
        backoff_factor = float(ncfg.get("backoff_factor", 0.5))
        status_forcelist = ncfg.get("status_forcelist", [500, 502, 503, 504])
        user_agent = str(ncfg.get("user_agent", "Mozilla/5.0"))

        retry = Retry(
            total=retry_total,
            connect=retry_total,
            read=retry_total,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=50, pool_maxsize=100)
        s = requests.Session()
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers.update({"User-Agent": user_agent})
        return s

    def safe_fetch(
        self,
        url: str,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Optional[requests.Response]:
        ncfg = self.cfg.get("network", {})
        timeout = (
            float(ncfg.get("timeout_connect", 5.0)),
            float(ncfg.get("timeout_read", 10.0)),
        )
        merged_headers: dict[str, str] = {}
        if headers:
            merged_headers.update(headers)
        try:
            r = self.session.get(url, params=params, headers=merged_headers or None, timeout=timeout)
            r.raise_for_status()
            return r
        except (RequestException, OSError, TimeoutError) as e:
            self.logger.error(f"[-] 请求失败: {url} | {e}")
            return None
        except ValueError as e:
            self.logger.error(f"[-] 请求参数无效: {url} | {e}")
            return None

    def load_history(self) -> dict[str, Any]:
        if not self.history_file.is_file():
            return {}
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as e:
            self.logger.warning(f"[!] 历史文件读取异常，使用空历史: {e}")
            return {}

    def atomic_write(self, data: dict[str, Any]) -> None:
        """原子写入历史文件：先写 .tmp 再 replace；Windows 发生锁定冲突时回退为直接覆盖。"""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.history_file.with_name(f"{self.history_file.stem}.tmp.{os.getpid()}{self.history_file.suffix}")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(self.history_file)
        except OSError as e:
            self.logger.warning(f"[!] atomic replace 失败,回退为直接覆盖: {e}")
            try:
                with open(self.history_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except OSError as write_err:
                self.logger.error(f"[-] 历史文件直接落盘失败: {write_err}")
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass

    def write_report_files(self, today: str, report_content: str) -> tuple[Path, Path]:
        report_dir = self.work_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        md_file = report_dir / f"strategy_report_{today}.md"
        txt_file = report_dir / f"strategy_report_{today}.txt"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(report_content + "\n")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(markdown_to_text(report_content) + "\n")
        return md_file, txt_file

    def history_series(self, hist: dict[str, Any], key: str) -> pd.Series:
        """从历史字典中提取指定 key 的时序数据，清洗后返回按日期排序的 float Series。

        自动剔除脏数据（非字符串 key 或非数值 value），无有效数据时返回空 Series(dtype=float)。
        """
        d = hist.get(key, {})
        if not isinstance(d, dict) or not d:
            return pd.Series(dtype=float)
        # 只接受 (str, 数值) 二元组,脏数据剔除后再排序
        clean: list[tuple[str, float]] = []
        for k, v in d.items():
            if not isinstance(k, str):
                continue
            fv = safe_float(v, math.nan)
            if math.isnan(fv):
                continue
            clean.append((k, fv))
        if not clean:
            return pd.Series(dtype=float)
        clean.sort(key=lambda x: x[0])
        return pd.Series([v for _, v in clean], dtype=float)

    # -------- crypto --------
    def _fetch_crypto_daily_ohlcv_binance(self, symbol: str) -> Optional[pd.DataFrame]:
        ccfg = self.cfg["crypto"]
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": f"{symbol}USDT", "interval": ccfg["interval"], "limit": ccfg["kline_limit"]}
        res = self.safe_fetch(url, params=params)
        if not res:
            return None
        try:
            data = res.json()
            if not isinstance(data, list) or len(data) < max(ccfg["ma_slow"] + 5, 80):
                return None
            rows = [
                {
                    "open": safe_float(x[1]),
                    "high": safe_float(x[2]),
                    "low": safe_float(x[3]),
                    "close": safe_float(x[4]),
                    "volume": safe_float(x[5]),
                }
                for x in data
                if isinstance(x, (list, tuple)) and len(x) >= 6
            ]
            return pd.DataFrame(rows)
        except Exception as e:
            self.logger.error(f"[-] 解析 Binance 日K失败 {symbol}: {e}")
            return None

    def _fetch_crypto_daily_ohlcv_binance_us(self, symbol: str) -> Optional[pd.DataFrame]:
        """通过 Binance.US 获取日线 OHLCV（Binance 主站在部分地区被封）。"""
        ccfg = self.cfg.get("crypto", {})
        url = "https://api.binance.us/api/v3/klines"
        params = {
            "symbol": f"{symbol}USDT",
            "interval": ccfg.get("interval", "1d"),
            "limit": ccfg.get("kline_limit", 100),
        }
        res = self.safe_fetch(url, params=params)
        if not res:
            return None
        try:
            data = res.json()
            if not isinstance(data, list) or len(data) < max(int(ccfg.get("ma_slow", 60)) + 5, 80):
                return None
            rows = [
                {
                    "open": safe_float(x[1]),
                    "high": safe_float(x[2]),
                    "low": safe_float(x[3]),
                    "close": safe_float(x[4]),
                    "volume": safe_float(x[5]),
                }
                for x in data
                if isinstance(x, (list, tuple)) and len(x) >= 6
            ]
            return pd.DataFrame(rows)
        except Exception as e:
            self.logger.error(f"[-] 解析 Binance.US 日K失败 {symbol}: {e}")
            return None

    def _fetch_crypto_daily_ohlcv_kucoin(self, symbol: str) -> Optional[pd.DataFrame]:
        ccfg = self.cfg.get("crypto", {})
        url = "https://api.kucoin.com/api/v1/market/candles"
        # KuCoin 默认只返回最近部分数据，需显式传递时间范围或依赖其默认 limit
        params = {
            "type": "1day",
            "symbol": f"{symbol}-USDT",
            "pageSize": str(ccfg.get("kline_limit", 100)),
        }
        res = self.safe_fetch(url, params=params)
        if not res:
            return None
        try:
            payload = res.json()
            if not isinstance(payload, dict):
                return None
            data = payload.get("data", [])
            if not isinstance(data, list) or len(data) < max(int(ccfg.get("ma_slow", 60)) + 5, 80):
                return None
            rows = [
                {
                    "open": safe_float(x[1]),
                    "close": safe_float(x[2]),
                    "high": safe_float(x[3]),
                    "low": safe_float(x[4]),
                    "volume": safe_float(x[5]),
                }
                for x in reversed(data)
                if isinstance(x, (list, tuple)) and len(x) >= 6
            ]
            return pd.DataFrame(rows)
        except Exception as e:
            self.logger.error(f"[-] 解析 KuCoin 日K失败 {symbol}: {e}")
            return None

    def fetch_crypto_daily_ohlcv(self, symbol: str) -> tuple[Optional[pd.DataFrame], Optional[str]]:
        providers: list[str] = self.cfg["crypto"].get("providers", ["kucoin", "binance_us"])
        for provider in providers:
            provider_key = str(provider).strip().lower()
            if provider_key == "binance":
                df = self._fetch_crypto_daily_ohlcv_binance(symbol)
            elif provider_key == "binance_us":
                df = self._fetch_crypto_daily_ohlcv_binance_us(symbol)
            elif provider_key == "kucoin":
                df = self._fetch_crypto_daily_ohlcv_kucoin(symbol)
            else:
                self.logger.warning(f"[!] 未识别的加密数据源，已跳过: {provider}")
                continue

            if df is not None and not df.empty:
                return df, provider_key
            self.logger.warning(f"[!] 加密数据源不可用，准备回退: {provider_key} -> {symbol}")

        return None, None

    def daily_decision_engine(self, df: pd.DataFrame) -> tuple[str, float, dict[str, Any]]:
        ccfg = self.cfg["crypto"]
        th = ccfg["score_thresholds"]

        # 数据不足时返回安全中性占位,让上层把它当作普通信号继续输出
        min_required = max(int(ccfg.get("ma_slow", 60)) + 2, 22)
        if df is None or df.empty or len(df) < min_required:
            self.logger.warning(
                f"[!] daily_decision_engine: 数据行数 {0 if df is None else len(df)} < {min_required},返回中性占位"
            )
            return (
                "⚪ 数据不足",
                0.0,
                {
                    "price": math.nan,
                    "daily_change": 0.0,
                    "rsi": math.nan,
                    "zscore": math.nan,
                    "score": 0.0,
                    "vol_ratio": 1.0,
                    "trend_up": False,
                    "position": "0%-0%",
                    "data_rows": 0 if df is None else int(len(df)),
                },
            )

        close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
        # 关键字段 NaN 兜底:即便行数够了,极端行情/数据源缺字段也可能在尾部留 NaN
        # 任一为 NaN 时返回中性占位,与 L302 行为保持一致(避免把"无信号"伪装成"弱信号")
        core_tail = pd.concat([close.iloc[-2:], high.iloc[-1:], low.iloc[-1:], vol.iloc[-1:]])
        if core_tail.isna().any():
            self.logger.warning(
                f"[!] daily_decision_engine: 核心 OHLCV 字段存在 NaN,返回中性占位 "
                f"(close[-2:]/high[-1]/low[-1]/vol[-1] 共 {core_tail.isna().sum()} 个 NaN)"
            )
            return (
                "⚪ 数据不足",
                0.0,
                {
                    "price": math.nan,
                    "daily_change": 0.0,
                    "rsi": math.nan,
                    "zscore": math.nan,
                    "score": 0.0,
                    "vol_ratio": 1.0,
                    "trend_up": False,
                    "position": "0%-0%",
                    "data_rows": int(len(df)),
                },
            )
        c, c_prev = close.iloc[-1], close.iloc[-2]
        daily_change = ((c - c_prev) / c_prev * 100) if c_prev > 0 else 0.0

        ma_fast = close.rolling(ccfg["ma_fast"]).mean().iloc[-1]
        ma_slow = close.rolling(ccfg["ma_slow"]).mean().iloc[-1]
        trend_up = c > ma_slow and ma_fast >= ma_slow

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(ccfg["rsi_period"]).mean()
        loss = (-delta.clip(upper=0)).rolling(ccfg["rsi_period"]).mean().replace(0, 1e-9)
        rsi = (100 - 100 / (1 + gain / loss)).iloc[-1]
        rsi_score = clamp((50 - rsi) / 20.0, -1, 1)

        ma_bb = close.rolling(ccfg["bb_period"]).mean().iloc[-1]
        std_bb = close.rolling(ccfg["bb_period"]).std().iloc[-1]
        std_bb = std_bb if std_bb and std_bb > 1e-12 else 1e-12
        z = (c - ma_bb) / std_bb
        bb_score = clamp(-z / 2.0, -1, 1)

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal
        macd_score = clamp((hist.iloc[-1] - hist.iloc[-2]) * 4.0, -1, 1)

        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        vol_ratio = (vol.iloc[-1] / vol_ma20) if vol_ma20 and vol_ma20 > 0 else 1.0
        vol_boost = clamp((vol_ratio - 1.0) * 0.3, -0.2, 0.2)

        raw_score = 0.35 * rsi_score + 0.35 * bb_score + 0.30 * macd_score + vol_boost

        prev_close = close.shift(1)
        true_ranges = pd.concat(
            [
                (high - low).abs(),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        )
        tr = true_ranges.max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        vol_regime = (atr / c) if c > 0 else 0
        penalty = clamp(vol_regime * ccfg["vol_scale"], 0, 0.5)
        score = raw_score * (1 - penalty)

        if not trend_up and score > th["buy"]:
            score = min(score, 0.25)
        if trend_up and score < th["sell"]:
            score = max(score, -0.25)

        if score >= th["strong_buy"]:
            advice, pos = "🟢 强势偏多（可分批）", "60%-80%"
        elif score >= th["buy"]:
            advice, pos = "🟡 温和偏多（观察加仓）", "30%-50%"
        elif score <= th["strong_sell"]:
            advice, pos = "🔴 强势偏空（减仓防守）", "0%-20%"
        elif score <= th["sell"]:
            advice, pos = "🟠 温和偏空（控制风险）", "20%-40%"
        else:
            advice, pos = "⚪ 中性震荡（等待确认）", "30%-50%"

        return advice, score, {
            "price": c, "daily_change": daily_change, "rsi": rsi, "zscore": z,
            "score": score, "vol_ratio": vol_ratio, "trend_up": trend_up, "position": pos,
            "data_rows": int(len(df)),
        }

    def analyze_crypto(self, name: str, symbol: str) -> tuple[Optional[str], Optional[float], Optional[str]]:
        df, provider = self.fetch_crypto_daily_ohlcv(symbol)
        if df is None or df.empty:
            return None, None, None
        try:
            advice, _, d = self.daily_decision_engine(df)
        except (IndexError, ValueError, KeyError) as e:
            # 引擎内已尽量防御,这里是最后一道兜底
            self.logger.error(f"[-] 决策引擎异常 {name}({symbol}): {e}")
            return None, None, None
        provider_text = (provider or "unknown").upper()
        msg = (
            f"- **{name} ({symbol})**: {d['price']:.2f} | 日变动 **{d['daily_change']:+.2f}%** | {advice}\n"
            f"  - 信号: score={d['score']:+.2f}, RSI={d['rsi']:.1f}, z={d['zscore']:+.2f}, "
            f"量比={d['vol_ratio']:.2f}, 趋势={'上行' if d['trend_up'] else '下行/震荡'}, 数据源={provider_text}, "
            f"K线行数={d.get('data_rows', 'N/A')}\n"
            f"  - 风控: 建议仓位 {d['position']}（日级观察，最小观察周期>=2天）"
        )
        return msg, d["price"], provider

    # -------- fund --------
    def classify_fund(self, name: str) -> str:
        rules = self.cfg["fund"]["category_rules"]
        for cat in ["QDII", "债基", "行业"]:
            kws = rules.get(cat, {}).get("include_keywords", [])
            if any(kw.lower() in name.lower() for kw in kws):
                return cat
        return "宽基"

    def _fetch_fund_estimate_eastmoney(self, code: str) -> tuple[Optional[float], Optional[float]]:
        """通过东方财富 API 获取基金最新净值和日涨跌幅。
        接口: api.fund.eastmoney.com/f10/lsjz ,返回纯 JSON。
        """
        url = "https://api.fund.eastmoney.com/f10/lsjz"
        params = {"fundCode": code, "pageIndex": 1, "pageSize": 1}
        res = self.safe_fetch(url, params=params, headers={"Referer": "https://fund.eastmoney.com/"})
        if not res:
            return None, None
        try:
            data = res.json()
            if not isinstance(data, dict):
                return None, None
            d_data = data.get("Data")
            if not isinstance(d_data, dict):
                return None, None
            items = d_data.get("LSJZList")
            if not isinstance(items, list) or not items:
                return None, None
            item = items[0]
            if not isinstance(item, dict):
                return None, None
            price = safe_float(item.get("DWJZ"), math.nan)
            daily = safe_float(item.get("JZZZL"), math.nan)
            if math.isnan(price):
                return None, None
            if math.isnan(daily):
                daily = 0.0
            return price, daily
        except Exception as e:
            self.logger.error(f"[-] 解析东方财富基金 API 失败 {code}: {e}")
            return None, None

    def fetch_fund_estimate(self, code: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
        providers: list[str] = self.cfg["fund"].get("providers", ["eastmoney_api"])
        for provider in providers:
            provider_key = str(provider).strip().lower()
            if provider_key == "eastmoney_api":
                price, daily = self._fetch_fund_estimate_eastmoney(code)
            else:
                self.logger.warning(f"[!] 未识别的基金数据源，已跳过: {provider}")
                continue

            if price is not None:
                return price, daily, provider_key
            self.logger.warning(f"[!] 基金数据源不可用，准备回退: {provider_key} -> {code}")

        return None, None, None

    def fund_metrics(self, hist: dict[str, Any], key: str, current_price: float) -> dict[str, Any]:
        """计算基金的 MA5 / MA20 指标，用于趋势判断。"""
        s = self.history_series(hist, key)
        if len(s) > 0:
            extra = pd.Series([current_price], dtype=float)
            s2 = pd.concat([s, extra], ignore_index=True)
        else:
            s2 = pd.Series([current_price], dtype=float)
        out = {"ma5": None, "ma20": None}
        if len(s2) >= 5:
            out["ma5"] = s2.iloc[-5:].mean()
        if len(s2) >= 20:
            out["ma20"] = s2.iloc[-20:].mean()
        return out

    def fund_advice(
        self,
        category: str,
        daily_change: float,
        ma5: Optional[float],
        ma20: Optional[float],
        price: float,
    ) -> tuple[str, str]:
        th = self.cfg["fund"]["thresholds"][category]
        trend = "中性"
        if ma5 is not None and ma20 is not None:
            if price > ma5 >= ma20:
                trend = "上行"
            elif price < ma5 <= ma20:
                trend = "下行"

        hot = daily_change >= th["daily_hot"]
        cold = daily_change <= th["daily_cold"]

        if hot and trend == "上行":
            return "🔴 偏热（分批止盈/降仓）", f"{category}阈值触发 + 上行后高位"
        if hot:
            return "🟠 偏热（谨慎追高）", f"{category}阈值触发"
        if cold and trend != "下行":
            return "🟢 偏冷（可小步补仓）", f"{category}阈值触发 + 非下行趋势"
        if cold:
            return "🟡 偏冷但趋势弱（观察）", f"{category}阈值触发 + 下行趋势"
        return "⚪ 区间中性", f"{category}阈值未触发"

    def fund_bucket(self, advice: str) -> str:
        if "偏热" in advice:
            return "hot"
        if "偏冷" in advice:
            return "cold"
        return "neutral"

    def analyze_fund(
        self,
        name: str,
        code: str,
        hist: dict[str, Any],
    ) -> tuple[Optional[str], Optional[float], Optional[str], Optional[str]]:
        price, daily_change, provider = self.fetch_fund_estimate(code)
        if price is None:
            return None, None, None, None

        category = self.classify_fund(name)
        m = self.fund_metrics(hist, f"FUND_{code}", price)
        advice, reason = self.fund_advice(category, daily_change, m["ma5"], m["ma20"], price)
        provider_text = (provider or "unknown").upper()

        if m["ma5"] is None or m["ma20"] is None:
            ma_txt = "N/A"
        else:
            ma_txt = f"MA5={m['ma5']:.4f}, MA20={m['ma20']:.4f}"

        msg = (
            f"- **{name} [{code}]** ({category}): {price:.4f} | 日变动 **{daily_change:+.2f}%** | {advice}\n"
            f"  - 诊断: {reason} | {ma_txt} | 数据源={provider_text}"
        )
        return msg, price, provider, self.fund_bucket(advice)

    def _primary_provider(self, kind: str) -> Optional[str]:
        """取 providers 列表首项;列表为空时返回 None(后续比较恒为'备援')。"""
        providers = self.cfg[kind].get("providers") or []
        if not providers:
            return None
        return str(providers[0]).strip().lower()

    def _scan_crypto(
        self,
        report: list[str],
        hist: dict[str, Any],
        today: str,
        primary: Optional[str],
    ) -> tuple[int, list[str]]:
        """跑加密资产分析,返回 (有效数, 备援列表)。"""
        report.append("**[加密资产 | 日线多因子]**")
        valid = 0
        fallbacks: list[str] = []
        for c in self.crypto_products:
            msg, price, provider = self.analyze_crypto(c["name"], c["symbol"])
            if not msg:
                continue
            report.append(msg)
            hist.setdefault(f"CRYPTO_{c['symbol']}", {})[today] = price
            valid += 1
            if provider and provider != primary:
                fallbacks.append(f"{c['name']}({c['symbol']}) -> {provider.upper()}")
        return valid, fallbacks

    def _scan_funds(
        self,
        report: list[str],
        hist: dict[str, Any],
        today: str,
        primary: Optional[str],
    ) -> tuple[int, list[str], dict[str, list[str]]]:
        """跑基金分析,返回 (有效数, 备援列表, 分桶后的报告段)。"""
        report.append("\n**[基金 | 分类阈值模型（QDII/债基/行业/宽基）]**")
        valid = 0
        fallbacks: list[str] = []
        sections: dict[str, list[str]] = {"hot": [], "cold": [], "neutral": []}
        for f in self.etf_products:
            msg, price, provider, bucket = self.analyze_fund(f["name"], f["code"], hist)
            if not msg:
                continue
            sections[bucket or "neutral"].append(msg)
            hist.setdefault(f"FUND_{f['code']}", {})[today] = price
            valid += 1
            if provider and provider != primary:
                fallbacks.append(f"{f['name']}[{f['code']}] -> {provider.upper()}")
        return valid, fallbacks, sections

    def _render_fund_sections(self, report: list[str], sections: dict[str, list[str]]) -> None:
        """把分桶后的基金段拼到 report。中性段超阈值时折叠。"""
        titles = [("hot", "🔥 偏热"), ("cold", "🧊 偏冷"), ("neutral", "⚪ 中性")]
        for key, title in titles:
            items = sections[key]
            report.append(f"\n***{title}（{len(items)}）***")
            if not items:
                report.append("- 无")
                continue
            if key == "neutral" and len(items) > self.max_neutral_funds_in_report:
                visible = items[: self.max_neutral_funds_in_report]
                hidden = len(items) - self.max_neutral_funds_in_report
                report.extend(visible)
                report.append(f"- 其余 {hidden} 条中性基金已省略，可按需查看明细文件")
            else:
                report.extend(items)

    def _build_fallback_summary(
        self,
        crypto_fb: list[str],
        fund_fb: list[str],
    ) -> str:
        """生成数据源备援摘要文本。"""
        lines = ["**[数据源备援摘要]**"]
        if crypto_fb:
            lines.append(f"- 加密资产备援 {len(crypto_fb)} 个: " + "；".join(crypto_fb))
        else:
            lines.append("- 加密资产: 今日未触发备援")
        if fund_fb:
            lines.append(f"- 基金备援 {len(fund_fb)} 个: " + "；".join(fund_fb))
        else:
            lines.append("- 基金: 今日未触发备援")
        return "\n".join(lines) + "\n"

    def run(self):
        self.logger.info("=== 🚀 日报监控启动（配置驱动）===")
        cfg_msg = (
            f"配置文件: {self.config_path} | "
            f"项目根: {self.project_dir} | "
            f"工作目录: {self.work_dir}"
        )
        self.logger.info(cfg_msg)
        hist = self.load_history()
        today = datetime.now().strftime("%Y-%m-%d")

        report: list[str] = [f"📊 **策略日报 ({today})**\n"]
        crypto_primary = self._primary_provider("crypto")
        fund_primary = self._primary_provider("fund")

        crypto_valid, crypto_fb = self._scan_crypto(report, hist, today, crypto_primary)
        fund_valid, fund_fb, sections = self._scan_funds(report, hist, today, fund_primary)
        valid_count = crypto_valid + fund_valid

        self._render_fund_sections(report, sections)

        if valid_count == 0:
            self.logger.error("❌ 未获取到有效行情，退出。")
            # 退出前把已累积的 hist 兜底落盘,避免下次启动从破损历史恢复
            try:
                self.atomic_write(hist)
            except OSError as e:
                self.logger.error(f"[-] 退出前落盘失败: {e}")
            sys.exit(1)

        self.atomic_write(hist)

        report.insert(1, self._build_fallback_summary(crypto_fb, fund_fb))
        report_content = "\n".join(report)
        md_file, txt_file = self.write_report_files(today, report_content)

        print("\n" + "=" * 88)
        print(report_content)
        print("=" * 88 + "\n")
        self.logger.info(f"✅ 完成，写入历史点位 {valid_count} 条")
        self.logger.info(f"📝 报告已输出: {md_file}")
        self.logger.info(f"📝 文本已输出: {txt_file}")


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_PATH
    app = QuantReporter(config_path)
    app.run()


if __name__ == "__main__":
    main()
