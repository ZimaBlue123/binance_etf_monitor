#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import json
import math
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import yaml


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "strategy_config.yaml"


def configure_console_encoding():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


configure_console_encoding()


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    if p.suffix.lower() in [".yaml", ".yml"]:
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    if p.suffix.lower() == ".json":
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    raise ValueError("仅支持 .yaml/.yml/.json 配置文件")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def clamp(x: float, low: float, high: float) -> float:
    return max(low, min(high, x))


def markdown_to_text(content: str) -> str:
    text = content.replace("**", "")
    text = text.replace("📊 ", "").replace("🟢 ", "").replace("🟡 ", "")
    text = text.replace("🔴 ", "").replace("🟠 ", "").replace("⚪ ", "")
    return text


class QuantReporter:
    def __init__(self, config_path: str):
        self.config_path = Path(config_path).expanduser().resolve()
        self.project_dir = self.config_path.parent.parent if self.config_path.parent.name == "config" else self.config_path.parent
        self.cfg = load_config(str(self.config_path))

        self.work_dir = self._resolve_path(self.cfg["work_dir"])
        self.work_dir.mkdir(parents=True, exist_ok=True)

        paths = self.cfg["paths"]
        self.log_file = self.work_dir / paths["log_file"]
        self.history_file = self.work_dir / paths["history_file"]
        self.etf_file = self._resolve_path(paths["etf_products_file"])
        self.crypto_file = self._resolve_path(paths["crypto_products_file"])

        os.environ["TZ"] = self.cfg.get("timezone", "Asia/Shanghai")
        try:
            time.tzset()
        except Exception:
            pass

        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(self.log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
        )
        self.logger = logging.getLogger(__name__)

        self.session = self._build_session()
        self.crypto_products = load_json(str(self.crypto_file))
        self.etf_products = load_json(str(self.etf_file))
        self.max_neutral_funds_in_report = int(
            self.cfg.get("fund", {}).get("report", {}).get("max_neutral_items", 20)
        )

    def _resolve_path(self, raw_path: str) -> Path:
        p = Path(raw_path).expanduser()
        if p.is_absolute():
            return p
        return (self.project_dir / p).resolve()

    def _build_session(self) -> requests.Session:
        ncfg = self.cfg["network"]
        retry = Retry(
            total=ncfg["retry_total"],
            connect=ncfg["retry_total"],
            read=ncfg["retry_total"],
            backoff_factor=ncfg["backoff_factor"],
            status_forcelist=ncfg["status_forcelist"],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=50, pool_maxsize=100)
        s = requests.Session()
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers.update({"User-Agent": ncfg["user_agent"]})
        return s

    def safe_fetch(self, url: str, params: Optional[dict] = None) -> Optional[requests.Response]:
        ncfg = self.cfg["network"]
        timeout = (ncfg["timeout_connect"], ncfg["timeout_read"])
        try:
            r = self.session.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            self.logger.error(f"[-] 请求失败: {url} | {e}")
            return None

    def load_history(self) -> Dict:
        if not self.history_file.exists():
            return {}
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"[!] 历史文件读取异常，使用空历史: {e}")
            return {}

    def atomic_write(self, data: Dict):
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.history_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(self.history_file)

    def write_report_files(self, today: str, report_content: str):
        report_dir = self.work_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        md_file = report_dir / f"strategy_report_{today}.md"
        txt_file = report_dir / f"strategy_report_{today}.txt"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(report_content + "\n")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(markdown_to_text(report_content) + "\n")
        return md_file, txt_file

    def history_series(self, hist: Dict, key: str) -> pd.Series:
        d = hist.get(key, {})
        if not d:
            return pd.Series(dtype=float)
        items = sorted(d.items(), key=lambda x: x[0])
        vals = [safe_float(v, math.nan) for _, v in items]
        return pd.Series(vals).dropna()

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
            rows = [{
                "open": safe_float(x[1]),
                "high": safe_float(x[2]),
                "low": safe_float(x[3]),
                "close": safe_float(x[4]),
                "volume": safe_float(x[5]),
            } for x in data]
            return pd.DataFrame(rows)
        except Exception as e:
            self.logger.error(f"[-] 解析 Binance 日K失败 {symbol}: {e}")
            return None

    def _fetch_crypto_daily_ohlcv_kucoin(self, symbol: str) -> Optional[pd.DataFrame]:
        ccfg = self.cfg["crypto"]
        url = "https://api.kucoin.com/api/v1/market/candles"
        params = {"type": "1day", "symbol": f"{symbol}-USDT"}
        res = self.safe_fetch(url, params=params)
        if not res:
            return None
        try:
            payload = res.json()
            data = payload.get("data", [])
            if not isinstance(data, list) or len(data) < max(ccfg["ma_slow"] + 5, 80):
                return None
            rows = [{
                "open": safe_float(x[1]),
                "close": safe_float(x[2]),
                "high": safe_float(x[3]),
                "low": safe_float(x[4]),
                "volume": safe_float(x[5]),
            } for x in reversed(data)]
            return pd.DataFrame(rows)
        except Exception as e:
            self.logger.error(f"[-] 解析 KuCoin 日K失败 {symbol}: {e}")
            return None

    def fetch_crypto_daily_ohlcv(self, symbol: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        providers: List[str] = self.cfg["crypto"].get("providers", ["binance", "kucoin"])
        for provider in providers:
            provider_key = str(provider).strip().lower()
            if provider_key == "binance":
                df = self._fetch_crypto_daily_ohlcv_binance(symbol)
            elif provider_key == "kucoin":
                df = self._fetch_crypto_daily_ohlcv_kucoin(symbol)
            else:
                self.logger.warning(f"[!] 未识别的加密数据源，已跳过: {provider}")
                continue

            if df is not None and not df.empty:
                return df, provider_key
            self.logger.warning(f"[!] 加密数据源不可用，准备回退: {provider_key} -> {symbol}")

        return None, None

    def daily_decision_engine(self, df: pd.DataFrame) -> Tuple[str, float, Dict]:
        ccfg = self.cfg["crypto"]
        th = ccfg["score_thresholds"]

        close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
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

        tr = pd.concat([(high - low).abs(), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
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
            "score": score, "vol_ratio": vol_ratio, "trend_up": trend_up, "position": pos
        }

    def analyze_crypto(self, name: str, symbol: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
        df, provider = self.fetch_crypto_daily_ohlcv(symbol)
        if df is None or df.empty:
            return None, None, None
        advice, _, d = self.daily_decision_engine(df)
        provider_text = (provider or "unknown").upper()
        msg = (
            f"- **{name} ({symbol})**: {d['price']:.2f} | 日变动 **{d['daily_change']:+.2f}%** | {advice}\n"
            f"  - 信号: score={d['score']:+.2f}, RSI={d['rsi']:.1f}, z={d['zscore']:+.2f}, "
            f"量比={d['vol_ratio']:.2f}, 趋势={'上行' if d['trend_up'] else '下行/震荡'}, 数据源={provider_text}\n"
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

    def _fetch_fund_estimate_fundgz(self, code: str) -> Tuple[Optional[float], Optional[float]]:
        url = f"https://fundgz.1234567.com.cn/js/{code}.js"
        res = self.safe_fetch(url)
        if not res:
            return None, None
        try:
            m = re.search(r"jsonpgz\s*\(\s*({.*?})\s*\)\s*;", res.text)
            if not m:
                return None, None
            d = json.loads(m.group(1))
            price = safe_float(d.get("gsz"), math.nan)
            daily = safe_float(d.get("gszzl"), math.nan)
            if math.isnan(price) or math.isnan(daily):
                return None, None
            return price, daily
        except Exception as e:
            self.logger.error(f"[-] 解析 FundGZ 基金数据失败 {code}: {e}")
            return None, None

    def _fetch_fund_estimate_eastmoney_f10(self, code: str) -> Tuple[Optional[float], Optional[float]]:
        url = f"https://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=1"
        res = self.safe_fetch(url)
        if not res:
            return None, None
        try:
            row_match = re.search(r"<tbody><tr>(.*?)</tr>", res.text, flags=re.S | re.I)
            if not row_match:
                return None, None
            cols = re.findall(r"<td[^>]*>(.*?)</td>", row_match.group(1), flags=re.S | re.I)
            if len(cols) < 4:
                return None, None
            price = safe_float(re.sub(r"<.*?>", "", cols[1]).strip(), math.nan)
            daily_text = re.sub(r"<.*?>", "", cols[3]).replace("%", "").strip()
            daily = safe_float(daily_text, math.nan)
            if math.isnan(price):
                return None, None
            if math.isnan(daily):
                daily = 0.0
            return price, daily
        except Exception as e:
            self.logger.error(f"[-] 解析 Eastmoney F10 基金数据失败 {code}: {e}")
            return None, None

    def fetch_fund_estimate(self, code: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        providers: List[str] = self.cfg["fund"].get("providers", ["fundgz", "eastmoney_f10"])
        for provider in providers:
            provider_key = str(provider).strip().lower()
            if provider_key == "fundgz":
                price, daily = self._fetch_fund_estimate_fundgz(code)
            elif provider_key == "eastmoney_f10":
                price, daily = self._fetch_fund_estimate_eastmoney_f10(code)
            else:
                self.logger.warning(f"[!] 未识别的基金数据源，已跳过: {provider}")
                continue

            if price is not None:
                return price, daily, provider_key
            self.logger.warning(f"[!] 基金数据源不可用，准备回退: {provider_key} -> {code}")

        return None, None, None

    def fund_metrics(self, hist: Dict, key: str, current_price: float) -> Dict:
        s = self.history_series(hist, key)
        s2 = pd.concat([s, pd.Series([current_price])], ignore_index=True) if len(s) > 0 else pd.Series([current_price])
        out = {"ma5": None, "ma20": None}
        if len(s2) >= 5:
            out["ma5"] = s2.iloc[-5:].mean()
        if len(s2) >= 20:
            out["ma20"] = s2.iloc[-20:].mean()
        return out

    def fund_advice(self, category: str, daily_change: float, ma5, ma20, price) -> Tuple[str, str]:
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

    def analyze_fund(self, name: str, code: str, hist: Dict) -> Tuple[Optional[str], Optional[float], Optional[str], Optional[str]]:
        price, daily_change, provider = self.fetch_fund_estimate(code)
        if price is None:
            return None, None, None, None

        category = self.classify_fund(name)
        m = self.fund_metrics(hist, f"FUND_{code}", price)
        advice, reason = self.fund_advice(category, daily_change, m["ma5"], m["ma20"], price)
        provider_text = (provider or "unknown").upper()

        ma_txt = "N/A" if m["ma5"] is None or m["ma20"] is None else f"MA5={m['ma5']:.4f}, MA20={m['ma20']:.4f}"

        msg = (
            f"- **{name} [{code}]** ({category}): {price:.4f} | 日变动 **{daily_change:+.2f}%** | {advice}\n"
            f"  - 诊断: {reason} | {ma_txt} | 数据源={provider_text}"
        )
        return msg, price, provider, self.fund_bucket(advice)

    def run(self):
        self.logger.info("=== 🚀 日报监控启动（配置驱动）===")
        hist = self.load_history()
        today = datetime.now().strftime("%Y-%m-%d")

        report = [f"📊 **策略日报 ({today})**\n"]
        valid_count = 0
        crypto_primary = str(self.cfg["crypto"].get("providers", ["binance"])[0]).strip().lower()
        fund_primary = str(self.cfg["fund"].get("providers", ["fundgz"])[0]).strip().lower()
        crypto_fallback_used = []
        fund_fallback_used = []
        fund_sections = {
            "hot": [],
            "cold": [],
            "neutral": [],
        }

        report.append("**[加密资产 | 日线多因子]**")
        for c in self.crypto_products:
            msg, price, provider = self.analyze_crypto(c["name"], c["symbol"])
            if msg:
                report.append(msg)
                hist.setdefault(f"CRYPTO_{c['symbol']}", {})[today] = price
                valid_count += 1
                if provider and provider != crypto_primary:
                    crypto_fallback_used.append(f"{c['name']}({c['symbol']}) -> {provider.upper()}")

        report.append("\n**[基金 | 分类阈值模型（QDII/债基/行业/宽基）]**")
        for f in self.etf_products:
            msg, price, provider, bucket = self.analyze_fund(f["name"], f["code"], hist)
            if msg:
                fund_sections[bucket or "neutral"].append(msg)
                hist.setdefault(f"FUND_{f['code']}", {})[today] = price
                valid_count += 1
                if provider and provider != fund_primary:
                    fund_fallback_used.append(f"{f['name']}[{f['code']}] -> {provider.upper()}")

        fund_group_titles = [
            ("hot", "🔥 偏热"),
            ("cold", "🧊 偏冷"),
            ("neutral", "⚪ 中性"),
        ]
        for key, title in fund_group_titles:
            items = fund_sections[key]
            report.append(f"\n***{title}（{len(items)}）***")
            if items:
                if key == "neutral" and len(items) > self.max_neutral_funds_in_report:
                    visible_items = items[:self.max_neutral_funds_in_report]
                    hidden_count = len(items) - self.max_neutral_funds_in_report
                    report.extend(visible_items)
                    report.append(f"- 其余 {hidden_count} 条中性基金已省略，可按需查看明细文件")
                else:
                    report.extend(items)
            else:
                report.append("- 无")

        if valid_count == 0:
            self.logger.error("❌ 未获取到有效行情，退出。")
            sys.exit(1)

        self.atomic_write(hist)

        summary = ["**[数据源备援摘要]**"]
        if crypto_fallback_used:
            summary.append(f"- 加密资产备援 {len(crypto_fallback_used)} 个: " + "；".join(crypto_fallback_used))
        else:
            summary.append("- 加密资产: 今日未触发备援")
        if fund_fallback_used:
            summary.append(f"- 基金备援 {len(fund_fallback_used)} 个: " + "；".join(fund_fallback_used))
        else:
            summary.append("- 基金: 今日未触发备援")
        report.insert(1, "\n".join(summary) + "\n")
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
