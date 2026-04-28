# Binance ETF Monitor

一个面向个人研究场景的周级监控脚本，用于同时跟踪加密资产和基金，并输出当日策略报告。

This project is a weekly monitoring script for personal research. It tracks both crypto assets and funds, then generates a daily strategy report in Markdown and plain text.

## 中文说明

### 项目用途

本项目以配置驱动方式运行：

- 读取 `config/strategy_config.yaml` 中的网络、阈值和路径配置
- 读取 `config/crypto_products.json` 和 `config/etf_products.json` 中的资产清单
- 拉取行情数据并生成周级观察结论
- 将日志、历史数据和报告写入本地 `output/`

适合本地运行、云主机定时执行、或接入任务计划程序。默认不依赖任何个人 API Key。

### 目录结构

- `binance_etf_configurable.py`：主程序入口
- `scriptsvalidate_strategy_assets.py`：项目自检脚本
- `config/strategy_config.yaml`：主配置文件
- `config/crypto_products.json`：加密资产列表
- `config/etf_products.json`：基金列表
- `run_monitor.bat`：Windows 一键运行主程序
- `validate_assets.bat`：Windows 一键执行自检
- `output/`：运行后生成的本地数据目录，不应提交

### 环境要求

- Python 3.10 或更高版本
- 依赖包：`pandas`、`requests`、`PyYAML`

安装示例：

```bash
pip install pandas requests pyyaml
```

### 快速开始

1. 先执行自检：

```bash
python scriptsvalidate_strategy_assets.py
```

或双击：

```text
validate_assets.bat
```

2. 运行主程序：

```bash
python binance_etf_configurable.py
```

或双击：

```text
run_monitor.bat
```

也可以在 Linux 云主机上运行：

```bash
chmod +x run_monitor.sh
./run_monitor.sh
```

### 输出文件

程序运行后会在 `output/` 下生成本地文件，例如：

- `output/logs/binance_etf.log`
- `output/data/fund_history.json`
- `output/reports/strategy_report_YYYY-MM-DD.md`
- `output/reports/strategy_report_YYYY-MM-DD.txt`

这些文件可能包含你的资产观察结果、运行习惯、历史记录或本地路径信息，建议仅本地保存，不要提交到代码仓库。

### 可配置项

- 增减基金：编辑 `config/etf_products.json`
- 增减加密资产：编辑 `config/crypto_products.json`
- 调整网络参数、输出目录、阈值：编辑 `config/strategy_config.yaml`
- 调整加密行情来源顺序：修改 `crypto.providers`
- 调整基金行情来源顺序：修改 `fund.providers`

### 隐私与安全

本仓库已经按“默认不泄露”原则整理：

- `output/`、日志、报告、缓存、历史数据应通过 `.gitignore` 排除
- `.env`、私钥、令牌、密钥文件不会纳入版本控制
- 当前项目未发现硬编码个人 API Key
- 如果后续接入私有通知渠道、Webhook 或云端密钥，请放入环境变量，不要写入源码或配置样例

### 上传 GitHub 前检查

建议在上传前逐项确认：

1. 当前目录中不包含 `output/` 下的报告、日志、历史数据
2. 不包含 `.env`、密钥文件、证书文件、私有脚本副本
3. 不包含本机绝对路径截图、导出报告或手工备份文件
4. 只保留当前生效配置，即 `config/` 目录下的正式文件
5. 上传前先运行一次：

```bash
python scriptsvalidate_strategy_assets.py
```

如果你初始化了 Git，还可以再本地检查一次：

```bash
git status
git add .
git diff --cached
```

重点确认暂存区里没有 `output/`、`.env`、日志、报告或其他私有文件。

### 定时执行示例

Windows 可使用“任务计划程序”，调用：

```text
run_monitor.bat
```

Linux 云主机可使用 `cron`。仓库已附带 `cron.example`，示例含义为“每周一到周五 18:30 执行一次主程序”。

推荐流程：

```bash
pip install -r requirements.txt
chmod +x run_monitor.sh
crontab -e
```

然后把 `cron.example` 中的路径改成你的部署目录后加入 crontab。

### 自检范围

`scriptsvalidate_strategy_assets.py` 会检查：

- 配置文件结构是否完整
- 基金列表是否格式正确、代码是否重复
- 加密资产列表是否格式正确、symbol 是否重复
- 基金分类规则与阈值是否一致
- 项目中是否存在运行产物，提醒不要提交私有报告和日志

## English Guide

### What This Project Does

This is a configuration-driven monitor that:

- loads network, threshold, and path settings from `config/strategy_config.yaml`
- loads crypto and fund watchlists from JSON files under `config/`
- fetches market data from public sources with fallback providers
- writes local logs, history, and daily reports into `output/`

It is suitable for local execution, scheduled runs on a server, or Windows Task Scheduler. No personal API key is required by default.

### Main Files

- `binance_etf_configurable.py`: main entry point
- `scriptsvalidate_strategy_assets.py`: self-check and repository hygiene validator
- `config/strategy_config.yaml`: main runtime configuration
- `config/crypto_products.json`: crypto watchlist
- `config/etf_products.json`: fund watchlist
- `run_monitor.bat`: one-click launcher for Windows
- `validate_assets.bat`: one-click validation for Windows

### Requirements

- Python 3.10+
- Dependencies: `pandas`, `requests`, `PyYAML`

Install:

```bash
pip install -r requirements.txt
```

### Usage

Run validation first:

```bash
python scriptsvalidate_strategy_assets.py
```

Then run the monitor:

```bash
python binance_etf_configurable.py
```

On Linux servers you can also use:

```bash
chmod +x run_monitor.sh
./run_monitor.sh
```

### Output and Privacy

Generated files under `output/` may include:

- runtime logs
- strategy reports
- locally accumulated history data
- machine-specific path traces in logs

These files are for local use only and should not be committed to a repository. The provided `.gitignore` is configured to exclude them.

### Configuration Notes

- edit `config/etf_products.json` to change funds
- edit `config/crypto_products.json` to change crypto assets
- edit `config/strategy_config.yaml` to change thresholds, providers, network behavior, and output paths

### GitHub Upload Checklist

Before pushing this project to GitHub, make sure that:

- there are no generated files under `output/`
- there is no `.env` file or any private key, token, certificate, or credential file
- only the active config files under `config/` are kept
- you run the validator before upload:

```bash
python scriptsvalidate_strategy_assets.py
```

If Git has been initialized locally, also inspect staged files carefully:

```bash
git status
git add .
git diff --cached
```

### Scheduling

- Windows: use Task Scheduler with `run_monitor.bat`
- Linux: use `cron` with `run_monitor.sh`
- an example cron entry is included in `cron.example`

## License

This project is released under the MIT License. See `LICENSE` for details.
