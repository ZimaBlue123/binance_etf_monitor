"""scripts/validate_strategy_assets.py 核心函数的单元测试。

覆盖范围:
- load_config:YAML/JSON 解析、空文件、非 dict 防御
- classify_fund:4 大类命中规则
- validate_thresholds:daily_hot > daily_cold 约束 + 缺字段
- validate_etf_products:代码格式、唯一性、空列表
- validate_crypto_products:symbol 格式、唯一性
- resolve_from_project:绝对/相对路径解析
- collect_runtime_artifacts:glob 命中
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 把 scripts/ 注入 sys.path,避免变成 package import(脚本不是包)
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_strategy_assets as vsa  # noqa: E402  (sys.path 注入后导入)


# ============================================================
#  load_config
# ============================================================

class TestLoadConfig:
    def test_yaml_dict(self, tmp_path: Path):
        p = tmp_path / "cfg.yaml"
        p.write_text("timezone: Asia/Shanghai\nwork_dir: out\n", encoding="utf-8")
        data = vsa.load_config(p)
        assert data["timezone"] == "Asia/Shanghai"
        assert data["work_dir"] == "out"

    def test_json_dict(self, tmp_path: Path):
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps({"k": 1}), encoding="utf-8")
        assert vsa.load_config(p) == {"k": 1}

    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            vsa.load_config(tmp_path / "nope.yaml")

    def test_unsupported_ext(self, tmp_path: Path):
        p = tmp_path / "cfg.toml"
        p.write_text("k=1", encoding="utf-8")
        with pytest.raises(ValueError, match="仅支持"):
            vsa.load_config(p)

    def test_yaml_root_not_dict(self, tmp_path: Path):
        p = tmp_path / "cfg.yaml"
        p.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ValueError, match="期望 dict"):
            vsa.load_config(p)

    def test_json_root_not_dict(self, tmp_path: Path):
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(ValueError, match="期望 dict"):
            vsa.load_config(p)


# ============================================================
#  classify_fund
# ============================================================

class TestClassifyFund:
    RULES = {
        "QDII": {"include_keywords": ["QDII", "纳斯达克"]},
        "债基": {"include_keywords": ["债", "中短债"]},
        "行业": {"include_keywords": ["医药", "半导体"]},
        "宽基": {"include_keywords": []},
    }

    @pytest.mark.parametrize("name,expected", [
        ("华夏纳斯达克100ETF(QDII)", "QDII"),
        ("易方达中短债债券A", "债基"),
        ("招商医药健康产业股票", "行业"),
        ("沪深300ETF", "宽基"),  # 都不命中
    ])
    def test_classify(self, name: str, expected: str):
        assert vsa.classify_fund(name, self.RULES) == expected

    def test_classify_empty_keywords(self):
        # 极端:所有规则关键词都是空,全部走"宽基"
        empty = {"QDII": {"include_keywords": []}, "债基": {"include_keywords": []},
                 "行业": {"include_keywords": []}, "宽基": {"include_keywords": []}}
        assert vsa.classify_fund("随便什么", empty) == "宽基"


# ============================================================
#  validate_thresholds
# ============================================================

class TestValidateThresholds:
    def test_ok(self):
        thr = {"QDII": {"daily_hot": 2.0, "daily_cold": -1.5}}
        assert vsa.validate_thresholds(thr) == []

    def test_hot_le_cold(self):
        thr = {"QDII": {"daily_hot": -1.0, "daily_cold": 1.0}}
        errs = vsa.validate_thresholds(thr)
        assert any("daily_hot 必须 > daily_cold" in e for e in errs)

    def test_hot_eq_cold(self):
        thr = {"QDII": {"daily_hot": 0.0, "daily_cold": 0.0}}
        assert any("daily_hot 必须 > daily_cold" in e for e in vsa.validate_thresholds(thr))

    def test_missing_key(self):
        thr = {"QDII": {"daily_hot": 1.0}}  # 缺 daily_cold
        errs = vsa.validate_thresholds(thr)
        assert any("缺少字段 `daily_cold`" in e for e in errs)

    def test_non_dict_category(self):
        thr = {"QDII": "not a dict"}
        errs = vsa.validate_thresholds(thr)
        assert any("不是对象" in e for e in errs)


# ============================================================
#  validate_etf_products
# ============================================================

class TestValidateEtfProducts:
    def test_ok(self):
        items = [{"code": "000001", "name": "华夏成长"}, {"code": "510300", "name": "沪深300"}]
        assert vsa.validate_etf_products(items) == []

    def test_duplicate_code(self):
        items = [{"code": "000001", "name": "A"}, {"code": "000001", "name": "B"}]
        errs = vsa.validate_etf_products(items)
        assert any("重复基金代码" in e for e in errs)

    def test_invalid_code_format(self):
        items = [{"code": "abc", "name": "X"}]  # 不是6位数字
        errs = vsa.validate_etf_products(items)
        assert any("code 非法" in e for e in errs)

    def test_missing_name(self):
        items = [{"code": "000001", "name": ""}]
        errs = vsa.validate_etf_products(items)
        assert any("缺少 name" in e for e in errs)

    def test_non_list_root(self):
        errs = vsa.validate_etf_products({"oops": True})  # type: ignore[arg-type]
        assert any("顶层必须是数组" in e for e in errs)


# ============================================================
#  validate_crypto_products
# ============================================================

class TestValidateCryptoProducts:
    def test_ok(self):
        items = [{"symbol": "BTC", "name": "Bitcoin"}, {"symbol": "ETH", "name": "Ethereum"}]
        assert vsa.validate_crypto_products(items) == []

    def test_duplicate_symbol_case_insensitive(self):
        items = [{"symbol": "btc", "name": "X"}, {"symbol": "BTC", "name": "Y"}]
        errs = vsa.validate_crypto_products(items)
        assert any("重复币种代码" in e for e in errs)

    def test_invalid_symbol_chars(self):
        items = [{"symbol": "BT-C", "name": "X"}]
        errs = vsa.validate_crypto_products(items)
        assert any("symbol 非法" in e for e in errs)


# ============================================================
#  resolve_from_project
# ============================================================

class TestResolveFromProject:
    def test_absolute(self, tmp_path: Path):
        cfg = tmp_path / "config" / "strategy_config.yaml"
        out = vsa.resolve_from_project(cfg, str(tmp_path / "abs.json"))
        assert out.is_absolute()
        assert str(out).endswith("abs.json")

    def test_relative(self, tmp_path: Path):
        cfg = tmp_path / "config" / "strategy_config.yaml"
        out = vsa.resolve_from_project(cfg, "data/x.json")
        assert out == (tmp_path / "data" / "x.json").resolve()


# ============================================================
#  collect_runtime_artifacts
# ============================================================

class TestCollectRuntimeArtifacts:
    def test_picks_up_files(self, tmp_path: Path):
        (tmp_path / "output" / "reports").mkdir(parents=True)
        (tmp_path / "output" / "reports" / "strategy_report_2024-01-01.md").write_text("x")
        (tmp_path / "output" / "logs").mkdir(parents=True)
        (tmp_path / "output" / "logs" / "a.log").write_text("y")
        results = vsa.collect_runtime_artifacts(tmp_path)
        names = sorted(p.name for p in results)
        assert "strategy_report_2024-01-01.md" in names
        assert "a.log" in names

    def test_no_artifacts(self, tmp_path: Path):
        assert vsa.collect_runtime_artifacts(tmp_path) == []
