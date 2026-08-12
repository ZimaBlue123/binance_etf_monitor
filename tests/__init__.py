"""Binance ETF Monitor — pytest 单元测试根包。

目录组织:
- tests/test_validate_strategy_assets.py    校验脚本核心逻辑
- tests/test_binance_etf_configurable.py    主程序纯函数(pandas 之外的轻量函数)

设计原则:
- 单元测试只覆盖无 I/O 副作用的纯函数,保证 CI 在沙箱里 < 5s 跑完
- 集成场景(API 请求 / 文件落盘)用 monkeypatch/mock,绝不真发请求
"""
