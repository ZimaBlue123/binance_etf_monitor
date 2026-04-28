#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
一键校验策略配置、资产清单与仓库卫生

校验项：
1) 配置文件可读取（yaml/json）
2) 必填字段完整
3) fund.thresholds 与 category_rules 类别一致
4) etf_products.json 格式正确、基金代码唯一、代码格式合法(6位数字)
5) crypto_products.json 格式正确、币种唯一、symbol 格式合法
6) 基金名称非空
7) 分类命中率统计（QDII/债基/行业/宽基）
8) 阈值字段完整且 daily_hot > daily_cold
9) 检查 output 等运行产物，提醒不要提交私有报告/日志/历史数据
10) 输出校验报告，异常时非0退出码
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import yaml


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "strategy_config.yaml"
REQUIRED_TOP_LEVEL = ["timezone", "work_dir", "paths", "network", "crypto", "fund"]
REQUIRED_PATHS = ["log_file", "history_file", "etf_products_file", "crypto_products_file"]
REQUIRED_THRESH_KEYS = ["daily_hot", "daily_cold"]
RUNTIME_ARTIFACT_PATTERNS = [
    "output/reports/*.md",
    "output/reports/*.txt",
    "output/logs/*.log",
    "output/data/*.json",
]


def configure_console_encoding():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


configure_console_encoding()


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    if path.suffix.lower() in [".yaml", ".yml"]:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError("配置文件仅支持 .yaml/.yml/.json")


def classify_fund(name: str, category_rules: Dict[str, dict]) -> str:
    lower_name = name.lower()
    for cat in ["QDII", "债基", "行业"]:
        kws = category_rules.get(cat, {}).get("include_keywords", [])
        if any(str(k).lower() in lower_name for k in kws):
            return cat
    return "宽基"


def validate_thresholds(thresholds: Dict[str, dict]) -> List[str]:
    errors = []
    for cat, conf in thresholds.items():
        for k in REQUIRED_THRESH_KEYS:
            if k not in conf:
                errors.append(f"[thresholds] 类别 `{cat}` 缺少字段 `{k}`")
        if all(k in conf for k in REQUIRED_THRESH_KEYS):
            if conf["daily_hot"] <= conf["daily_cold"]:
                errors.append(f"[thresholds] `{cat}` daily_hot 必须 > daily_cold")
    return errors


def validate_etf_products(etf_list: list) -> Tuple[List[str], Dict[str, int]]:
    errors = []
    seen = {}
    class_stats = {"QDII": 0, "债基": 0, "行业": 0, "宽基": 0}  # 仅占位，实际在外部统计

    if not isinstance(etf_list, list):
        return ["etf_products.json 顶层必须是数组(list)"], class_stats

    for i, item in enumerate(etf_list):
        if not isinstance(item, dict):
            errors.append(f"[etf] 第 {i} 项不是对象")
            continue

        code = str(item.get("code", "")).strip()
        name = str(item.get("name", "")).strip()

        if not code:
            errors.append(f"[etf] 第 {i} 项缺少 code")
        elif not (len(code) == 6 and code.isdigit()):
            errors.append(f"[etf] 第 {i} 项 code 非法: `{code}`（应为6位数字）")

        if not name:
            errors.append(f"[etf] 第 {i} 项缺少 name")

        if code:
            seen[code] = seen.get(code, 0) + 1

    duplicates = [c for c, n in seen.items() if n > 1]
    if duplicates:
        errors.append(f"[etf] 发现重复基金代码 {len(duplicates)} 个，例如: {duplicates[:10]}")

    return errors, class_stats


def validate_crypto_products(crypto_list: list) -> List[str]:
    errors = []
    seen = {}

    if not isinstance(crypto_list, list):
        return ["crypto_products.json 顶层必须是数组(list)"]

    for i, item in enumerate(crypto_list):
        if not isinstance(item, dict):
            errors.append(f"[crypto] 第 {i} 项不是对象")
            continue

        symbol = str(item.get("symbol", "")).strip().upper()
        name = str(item.get("name", "")).strip()

        if not symbol:
            errors.append(f"[crypto] 第 {i} 项缺少 symbol")
        elif not symbol.isalnum():
            errors.append(f"[crypto] 第 {i} 项 symbol 非法: `{symbol}`（应仅包含字母或数字）")

        if not name:
            errors.append(f"[crypto] 第 {i} 项缺少 name")

        if symbol:
            seen[symbol] = seen.get(symbol, 0) + 1

    duplicates = [s for s, n in seen.items() if n > 1]
    if duplicates:
        errors.append(f"[crypto] 发现重复币种代码 {len(duplicates)} 个，例如: {duplicates[:10]}")

    return errors


def resolve_from_project(config_path: Path, raw_path: str) -> Path:
    project_dir = config_path.parent.parent if config_path.parent.name == "config" else config_path.parent
    p = Path(raw_path).expanduser()
    if p.is_absolute():
        return p
    return (project_dir / p).resolve()


def collect_runtime_artifacts(project_dir: Path) -> List[Path]:
    matches: List[Path] = []
    for pattern in RUNTIME_ARTIFACT_PATTERNS:
        matches.extend(project_dir.glob(pattern))
    return sorted({path.resolve() for path in matches})


def main():
    config_path = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else DEFAULT_CONFIG_PATH
    project_dir = config_path.parent.parent if config_path.parent.name == "config" else config_path.parent

    errors: List[str] = []
    warnings: List[str] = []

    # 1) 读配置
    try:
        cfg = load_config(config_path)
    except Exception as e:
        print(f"❌ 配置读取失败: {e}")
        sys.exit(2)

    # 2) 配置结构校验
    for k in REQUIRED_TOP_LEVEL:
        if k not in cfg:
            errors.append(f"[config] 缺少顶层字段 `{k}`")

    paths = cfg.get("paths", {})
    for k in REQUIRED_PATHS:
        if k not in paths:
            errors.append(f"[config.paths] 缺少字段 `{k}`")

    fund_cfg = cfg.get("fund", {})
    category_rules = fund_cfg.get("category_rules", {})
    thresholds = fund_cfg.get("thresholds", {})

    # 3) 类别一致性
    required_cats = {"QDII", "债基", "行业", "宽基"}
    rule_cats = set(category_rules.keys())
    thr_cats = set(thresholds.keys())

    missing_rule = required_cats - rule_cats
    missing_thr = required_cats - thr_cats
    extra_rule = rule_cats - required_cats
    extra_thr = thr_cats - required_cats

    if missing_rule:
        errors.append(f"[fund.category_rules] 缺少类别: {sorted(missing_rule)}")
    if missing_thr:
        errors.append(f"[fund.thresholds] 缺少类别: {sorted(missing_thr)}")
    if extra_rule:
        warnings.append(f"[fund.category_rules] 存在额外类别: {sorted(extra_rule)}")
    if extra_thr:
        warnings.append(f"[fund.thresholds] 存在额外类别: {sorted(extra_thr)}")

    errors.extend(validate_thresholds(thresholds))

    # 4) 读取 ETF 清单
    etf_file = resolve_from_project(config_path, paths.get("etf_products_file", "config/etf_products.json"))
    if not etf_file.exists():
        errors.append(f"[etf] 文件不存在: {etf_file}")
        etf_list = []
    else:
        try:
            etf_list = json.loads(etf_file.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"[etf] JSON 解析失败: {e}")
            etf_list = []

    etf_errors, _ = validate_etf_products(etf_list)
    errors.extend(etf_errors)

    # 5) 读取 Crypto 清单
    crypto_file = resolve_from_project(config_path, paths.get("crypto_products_file", "config/crypto_products.json"))
    if not crypto_file.exists():
        errors.append(f"[crypto] 文件不存在: {crypto_file}")
        crypto_list = []
    else:
        try:
            crypto_list = json.loads(crypto_file.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"[crypto] JSON 解析失败: {e}")
            crypto_list = []

    errors.extend(validate_crypto_products(crypto_list))

    # 6) 分类命中率统计
    class_count = {"QDII": 0, "债基": 0, "行业": 0, "宽基": 0}
    unclassified_examples = []

    if isinstance(etf_list, list):
        for item in etf_list:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            cat = classify_fund(name, category_rules)
            class_count[cat] = class_count.get(cat, 0) + 1
            if cat == "宽基" and len(unclassified_examples) < 20:
                unclassified_examples.append(name)

    total = sum(class_count.values())
    if total == 0:
        warnings.append("ETF 列表为空或全部无效，无法统计分类命中率。")

    runtime_artifacts = collect_runtime_artifacts(project_dir)
    if runtime_artifacts:
        warnings.append(
            f"发现 {len(runtime_artifacts)} 个运行产物文件（报告/日志/历史数据）。建议仅本地保存，并通过 .gitignore 排除。"
        )

    # 7) 输出报告
    print("\n=== 策略资产校验报告 ===")
    print(f"配置文件: {config_path}")
    print(f"ETF 文件: {etf_file}")
    print(f"Crypto 文件: {crypto_file}")
    print(f"ETF 总数: {total}")
    print(f"Crypto 总数: {len(crypto_list) if isinstance(crypto_list, list) else 0}")

    print("\n[分类统计]")
    for k in ["QDII", "债基", "行业", "宽基"]:
        v = class_count.get(k, 0)
        pct = (v / total * 100) if total else 0
        print(f"- {k}: {v} ({pct:.1f}%)")

    if unclassified_examples:
        print("\n[宽基(默认分类)示例 - 前20]")
        for n in unclassified_examples:
            print(f"- {n}")

    if runtime_artifacts:
        print("\n[运行产物提示 - 前10]")
        for path in runtime_artifacts[:10]:
            try:
                print(f"- {path.relative_to(project_dir)}")
            except ValueError:
                print(f"- {path}")

    if warnings:
        print("\n[警告]")
        for w in warnings:
            print(f"⚠️ {w}")

    if errors:
        print("\n[错误]")
        for e in errors:
            print(f"❌ {e}")
        print(f"\n校验结果: 失败（错误 {len(errors)} 条，警告 {len(warnings)} 条）")
        sys.exit(1)

    print(f"\n校验结果: 通过（警告 {len(warnings)} 条）")
    sys.exit(0)


if __name__ == "__main__":
    main()
