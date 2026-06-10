# Contributing / 贡献指南

本仓库为单人研究脚本,但仍然欢迎补丁式改进。提交前请先读完本指南。

## 1. 开发环境

- Python 3.10+(本仓库已验证 3.10 / 3.14)
- 推荐使用虚拟环境:`python -m venv .venv && source .venv/bin/activate`
- 安装依赖:`pip install -r requirements.txt`

## 2. 提交前自检

每次改动后,本地至少运行一次:

```bash
python -m py_compile binance_etf_configurable.py
python -m py_compile scriptsvalidate_strategy_assets.py
python scriptsvalidate_strategy_assets.py
```

预期:编译无输出、validator 报告"校验结果:通过"。

## 3. 修改规范

### 3.1 配置驱动优先

任何**业务侧可调参数**必须先放进 `config/strategy_config.yaml` 或 `config/*.json`,
不要在源码里硬编码阈值、URL、资产列表、文件路径。

### 3.2 日志与异常

- 网络请求 / 文件 IO 失败:必须 `try/except` 后写日志,不要把异常抛到 `run()` 顶层。
- 新增方法请补充**类型注解**(本仓库已 `from __future__ import annotations`)。
- 防御性边界:DataFrame `iloc[-2]`、字典 key 缺失、配置项缺失,都要在函数入口校验。

### 3.3 提交粒度

- **一个 commit 一个目的**(区分 `feat:` / `fix:` / `refactor:` / `chore:` / `docs:` / `test:`)。
- 修改代码时,不要顺手改无关格式;以 `git diff` 看到的就是你意图提交的为准。

## 4. 仓库卫生红线

**以下内容绝不允许出现在 `git status` / `git diff` 中:**

- `output/` 下的报告、日志、历史数据
- `.env`、私钥、证书、Webhook URL
- 本机绝对路径、用户目录、临时导出
- `__pycache__/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`

仓库根的 `.gitignore` 已拦截上述类别,**新增类别请同步追加到 `.gitignore`**。

## 5. 提交流程

```bash
# 1. 自检
python scriptsvalidate_strategy_assets.py

# 2. 检查暂存区
git status
git diff

# 3. 暂存并提交(Conventional Commits 规范)
git add .
git commit -m "feat: 新增 XX"

# 4. 推送前确认远端
git remote -v
git push origin <branch>
```

## 6. Windows 特定问题

- `os.replace()` 在 Windows 上对被占用的目标文件偶发失败 —
  `atomic_write` 已封装 `OSError` 兜底,新增需要持久化的写入请复用该模式。
- `time.tzset()` 在 Windows 上不可用 — 日志会以 debug 级别记录"tzset 不可用",无需手动调用。
- `subprocess` / `requests` 输出含中文时,先 `reconfigure(encoding="utf-8", errors="replace")` —
  `configure_console_encoding()` 已实现,新增 CLI 入口请调用一次。

## 7. 反馈

发现问题优先开 Issue;若涉及安全隐私(例如某次提交意外暴露了持仓),请立即联系维护者,
**不要**在公开 Issue 中贴出敏感内容。
