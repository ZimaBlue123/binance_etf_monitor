#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键校验策略配置、资产清单与仓库卫生。

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

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml


__all__ = ["load_config", "classify_fund", "validate_thresholds", "validate_etf_products",
           "validate_crypto_products", "resolve_from_project", "collect_runtime_artifacts", "main"]


BASE_DIR = Path(__file__).resolve().parent.parent
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


def load_config(path: Path) -> dict[str, Any]:
    """读取并返回配置字典，支持 YAML 和 JSON 格式。"""
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    if path.suffix.lower() in [".yaml", ".yml"]:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"配置文件内容无效（期望 dict）: {path}")
        return data
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"配置文件内容无效（期望 dict）: {path}")
        return data
    raise ValueError("配置文件仅支持 .yaml/.yml/.json")


def classify_fund(name: str, category_rules: dict[str, dict[str, Any]]) -> str:
    lower_name = name.lower()
    for cat in ["QDII", "债基", "行业"]:
        kws = category_rules.get(cat, {}).get("include_keywords", [])
        if any(str(k).lower() in lower_name for k in kws):
            return cat
    return "宽基"


def validate_thresholds(thresholds: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for cat, conf in thresholds.items():
        if not isinstance(conf, dict):
            errors.append(f"[thresholds] 类别 `{cat}` 不是对象")
            continue
        for k in REQUIRED_THRESH_KEYS:
            if k not in conf:
                errors.append(f"[thresholds] 类别 `{cat}` 缺少字段 `{k}`")
        if all(k in conf for k in REQUIRED_THRESH_KEYS):
            if conf["daily_hot"] <= conf["daily_cold"]:
                errors.append(f"[thresholds] `{cat}` daily_hot 必须 > daily_cold")
    return errors


def validate_etf_products(etf_list: list[Any]) -> list[str]:
    """校验 ETF 清单格式：结构、字段完整性、代码唯一性。"""
    errors: list[str] = []
    seen: dict[str, int] = {}

    if not isinstance(etf_list, list):
        return ["etf_products.json 顶层必须是数组(list)"]

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

    return errors


def validate_crypto_products(crypto_list: list[Any]) -> list[str]:
    """校验加密资产清单格式：结构、字段完整性、symbol 唯一性。"""
    errors: list[str] = []
    seen: dict[str, int] = {}

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


def collect_runtime_artifacts(project_dir: Path) -> list[Path]:
    matches: list[Path] = []
    for pattern in RUNTIME_ARTIFACT_PATTERNS:
        matches.extend(project_dir.glob(pattern))
    return sorted({path.resolve() for path in matches})


def _check_required_top_level(cfg: dict, errors: list) -> dict:
    """返回 paths 字段(后续步骤用),顺手补 errors。"""
    for k in REQUIRED_TOP_LEVEL:
        if k not in cfg:
            errors.append(f"[config] 缺少顶层字段 `{k}`")
    paths = cfg.get("paths", {})
    for k in REQUIRED_PATHS:
        if k not in paths:
            errors.append(f"[config.paths] 缺少字段 `{k}`")
    return paths


def _check_category_consistency(category_rules, thresholds, errors, warnings):
    """类别是否齐全、有无多余。errors/warnings 原地填充。"""
    required = {"QDII", "债基", "行业", "宽基"}
    rule_cats = set(category_rules.keys())
    thr_cats = set(thresholds.keys())
    missing_rule = required - rule_cats
    missing_thr = required - thr_cats
    extra_rule = rule_cats - required
    extra_thr = thr_cats - required
    if missing_rule:
        errors.append(f"[fund.category_rules] 缺少类别: {sorted(missing_rule)}")
    if missing_thr:
        errors.append(f"[fund.thresholds] 缺少类别: {sorted(missing_thr)}")
    if extra_rule:
        warnings.append(f"[fund.category_rules] 存在额外类别: {sorted(extra_rule)}")
    if extra_thr:
        warnings.append(f"[fund.thresholds] 存在额外类别: {sorted(extra_thr)}")
    errors.extend(validate_thresholds(thresholds))


def _load_product_list(file_path: Path, kind: str, errors: list) -> list:
    """读 JSON 资产清单,失败时 errors 收集一条并返回 []。"""
    if not file_path.exists():
        errors.append(f"[{kind}] 文件不存在: {file_path}")
        return []
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"[{kind}] JSON 解析失败: {e}")
        return []


def _classify_funds(etf_list, category_rules):
    """统计分类命中,返回 (class_count, unclassified_examples)。"""
    counts = {"QDII": 0, "债基": 0, "行业": 0, "宽基": 0}
    examples: list = []
    if not isinstance(etf_list, list):
        return counts, examples
    for item in etf_list:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        cat = classify_fund(name, category_rules)
        counts[cat] = counts.get(cat, 0) + 1
        if cat == "宽基" and len(examples) < 20:
            examples.append(name)
    return counts, examples


def _print_header(config_path, etf_file, crypto_file, etf_total, crypto_total) -> None:
    """报告头部 + 资产清单统计。"""
    print("\n=== 策略资产校验报告 ===")
    print(f"配置文件: {config_path}")
    print(f"ETF 文件: {etf_file}")
    print(f"Crypto 文件: {crypto_file}")
    print(f"ETF 总数: {etf_total}")
    print(f"Crypto 总数: {crypto_total}")


def _print_classification(class_count, etf_total, unclassified_examples) -> None:
    """分类命中 + 宽基示例段。"""
    print("\n[分类统计]")
    for k in ["QDII", "债基", "行业", "宽基"]:
        v = class_count.get(k, 0)
        pct = (v / etf_total * 100) if etf_total else 0
        print(f"- {k}: {v} ({pct:.1f}%)")

    if not unclassified_examples:
        return
    print("\n[宽基(默认分类)示例 - 前20]")
    for n in unclassified_examples:
        print(f"- {n}")


def _print_artifacts(runtime_artifacts, project_dir) -> None:
    """运行产物提示段。"""
    if not runtime_artifacts:
        return
    print("\n[运行产物提示 - 前10]")
    for path in runtime_artifacts[:10]:
        try:
            print(f"- {path.relative_to(project_dir)}")
        except ValueError:
            print(f"- {path}")


def _print_warnings_and_errors(errors, warnings) -> None:
    """警告与错误段;errors 非空时 sys.exit(1)。"""
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


def _print_report(
    config_path, etf_file, crypto_file, etf_total, crypto_total,
    class_count, unclassified_examples, runtime_artifacts, project_dir,
    errors, warnings,
):
    """格式化输出校验报告。"""
    _print_header(config_path, etf_file, crypto_file, etf_total, crypto_total)
    _print_classification(class_count, etf_total, unclassified_examples)
    _print_artifacts(runtime_artifacts, project_dir)
    _print_warnings_and_errors(errors, warnings)


def main():
    config_path = (
        Path(sys.argv[1]).expanduser().resolve()
        if len(sys.argv) > 1
        else DEFAULT_CONFIG_PATH
    )
    parent_name = config_path.parent.name
    base = config_path.parent
    project_dir = base.parent if parent_name == "config" else base

    errors: list = []
    warnings: list = []

    try:
        cfg = load_config(config_path)
    except Exception as e:
        print(f"❌ 配置读取失败: {e}")
        sys.exit(2)

    paths = _check_required_top_level(cfg, errors)
    fund_cfg = cfg.get("fund", {})
    category_rules = fund_cfg.get("category_rules", {})
    thresholds = fund_cfg.get("thresholds", {})

    _check_category_consistency(category_rules, thresholds, errors, warnings)

    etf_file = resolve_from_project(
        config_path,
        paths.get("etf_products_file", "config/etf_products.json"),
    )
    etf_list = _load_product_list(etf_file, "etf", errors)
    errors.extend(validate_etf_products(etf_list))

    crypto_file = resolve_from_project(
        config_path,
        paths.get("crypto_products_file", "config/crypto_products.json"),
    )
    crypto_list = _load_product_list(crypto_file, "crypto", errors)
    errors.extend(validate_crypto_products(crypto_list))

    class_count, unclassified_examples = _classify_funds(etf_list, category_rules)
    etf_total = sum(class_count.values())
    if etf_total == 0:
        warnings.append("ETF 列表为空或全部无效，无法统计分类命中率。")

    runtime_artifacts = collect_runtime_artifacts(project_dir)
    if runtime_artifacts:
        warn_msg = (
            f"发现 {len(runtime_artifacts)} 个运行产物文件"
            f"（报告/日志/历史数据）。建议仅本地保存，并通过 .gitignore 排除。"
        )
        warnings.append(warn_msg)

    _print_report(
        config_path=config_path,
        etf_file=etf_file,
        crypto_file=crypto_file,
        etf_total=etf_total,
        crypto_total=len(crypto_list) if isinstance(crypto_list, list) else 0,
        class_count=class_count,
        unclassified_examples=unclassified_examples,
        runtime_artifacts=runtime_artifacts,
        project_dir=project_dir,
        errors=errors,
        warnings=warnings,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
