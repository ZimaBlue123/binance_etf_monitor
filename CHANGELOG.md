# Changelog

本文件记录所有值得留痕的改动。格式参考 [Keep a Changelog](https://keepachangelog.com/),
版本号遵循 [Semantic Versioning](https://semver.org/)。

## [Unreleased]

### Changed — ETF 清单更新 & 代码健壮性补强(2026-06-18)

#### `config/etf_products.json`

- **更新**:ETF 基金观察清单更新至 150 只，同步重新构建 Android APK (v1.2.1)。

#### `binance_etf_configurable.py`

- **加固**:`load_config` 增加 YAML 空文件/非 dict 返回值防御。
- **加固**:`markdown_to_text` 补全报告中新增 emoji（🔥/🧊/🚀/📝/✅）的清理。
- **优化**:KuCoin 数据源显式传递 `pageSize` 参数，确保拉取足够 K 线数据。
- **优化**:`fund_metrics` 中 `pd.concat` 显式指定 `dtype=float`，消除 FutureWarning。
- **规范**:添加模块 docstring 与 `__all__` 声明。

#### `scripts/validate_strategy_assets.py`

- **加固**:`load_config` 增加空文件防御（与主程序同步）。
- **规范**:补全函数 docstring，参数泛型类型注解完善（`list` → `list[Any]`）。

#### 仓库卫生

- **更新**:`.gitignore` 新增 `*.apk`、`*.aab`、`.worktrees/`、`android/app/build/` 拦截规则。
- **清理**:移除冗余 worktree 副本与旧版 archive-v1.0。

### Changed — 代码健壮性 & 工程质量(2026-06-10)

#### `binance_etf_configurable.py`

- **修复**:`atomic_write` 在 Windows 上 `os.replace` 偶发失败时不再拖垮 `run()`,
  自动回退为直接覆盖并清理 `.tmp`。
- **修复**:`run()` 在 `valid_count == 0` 退出前,先把已累积的 `hist` 落盘,
  避免下次启动从破损/缺失历史中恢复。
- **修复**:`daily_decision_engine` 入口加 `len(df) < max(ma_slow+2, 22)` 校验,
  数据不足时返回安全中性占位(advice="⚪ 数据不足", score=0.0, position="0%-0%"),
  `analyze_crypto` 同步加 `IndexError/ValueError/KeyError` 兜底。
- **修复**:`load_json` 区分 `FileNotFoundError` 与 `JSONDecodeError`,给出清晰错误信息。
- **修复**:`history_series` 加类型校验,剔除 (str, 数值) 之外的脏数据后再排序。
- **修复**:`time.tzset()` 在 Windows 不可用时,把信息暂存到 `_pending_debug_logs`,
  logger 就绪后刷出,便于排查时区行为差异。
- **修复**:`run()` 启动时打印配置文件路径 / 项目根 / 工作目录,提升可观测性。
- **重构**:`providers` 列表可能为空时,主源 fallback 判定从 `IndexError` 改为 None 防御。
- **重构**:全文件添加 `from __future__ import annotations`,`Dict/List/Tuple`
  改用内置 `dict/list/tuple`。
- **可观测**:返回信号字典新增 `data_rows` 字段,日报中同步展示每只币的 K 线行数。

#### `scriptsvalidate_strategy_assets.py`

- **重构**:`validate_etf_products` 移除占位的 `class_stats` 返回值,签名
  `Tuple[List[str], Dict[str, int]]` → `list[str]`,`main()` 调用方同步更新。
- **加固**:`validate_thresholds` 增加对非 dict 类别的防御。
- **重构**:加 `from __future__ import annotations`,`Dict/List/Tuple` 改内置。

#### 仓库卫生

- **新增**:`.gitignore` 扩充 Windows 回收站、IDE 临时、Tox/Nox、egg-info、
  Jupyter checkpoint、profiling 文件、备份/补丁等条目。
- **新增**:`CONTRIBUTING.md` 开发与提交规范。
- **更新**:`requirements.txt` 钉死下界、放开上界,显式声明 `urllib3`。
- **更新**:本 changelog 文件。

#### `binance_etf_configurable.py` — 鲁棒性与类型

- **加固**:`safe_float` 补齐 Type Hints(`x: Any, default: float = 0.0) -> float`),
  `except Exception` 窄化为 `(TypeError, ValueError)`,匹配 `float()` 真实失败路径。
- **加固**:`daily_decision_engine` 在指标计算前对核心 OHLCV 尾部做 NaN 兜底,
  任一为 NaN 时返回与"数据不足"一致的中性占位,避免 NaN 蔓延到 score 输出。

#### 仓库结构 — 脚本规范化

- **重构**:自检脚本 `scriptsvalidate_strategy_assets.py` 重命名到
  `scripts/validate_strategy_assets.py`,与 `validate_assets.bat` 调用约定一致;
  `BASE_DIR` 同步上移一层指回 project root,保留 git rename history(`git mv` 等价)。
- **更新**:`README.md` / `CONTRIBUTING.md` 中所有引用同步到新路径。
- **更新**:`.gitignore` 补齐 Android/Gradle 类别(`.gradle/`、`.kotlin/`、
  `local.properties`、`captures/`、`*.hprof`、`.cxx/`、`android/app/{release,debug}/`)。

## [0.1.0] — 2026-06-09

### Added

- 加密资产 + 基金双轨监控
- 配置驱动(`config/strategy_config.yaml`)
- 多数据源 fallback(Binance / KuCoin;fundgz / eastmoney)
- 日度报告输出(Markdown + 纯文本)
- 资产清单自检脚本
- 隐私卫生 `.gitignore` 与 `cron.example`

[Unreleased]: https://github.com/ZimaBlue123/binance_etf_monitor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ZimaBlue123/binance_etf_monitor/releases/tag/v0.1.0
