#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Binance ETF Monitor — Chaquopy Python 端入口。"""

from __future__ import annotations

import io
import os
import sys
import threading
import traceback
import time
from pathlib import Path


class _CallbackStream(io.TextIOBase):
    """把 stdout / stderr 重定向到 Kotlin 端 callback 的简易代理。"""

    def __init__(self, callback, also_stdout: bool = False):
        self._cb = callback
        self._also = also_stdout
        self._buf = ""
        self._lock = threading.Lock()

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        if not s:
            return 0
        with self._lock:
            self._buf += s
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                self._emit(line + "\n")
        return len(s)

    def flush(self) -> None:
        with self._lock:
            if self._buf:
                self._emit(self._buf)
                self._buf = ""

    def _emit(self, line: str) -> None:
        if self._cb is not None:
            try:
                self._cb.emit(line)
                return
            except Exception:
                pass
        if self._also:
            try:
                sys.__stdout__.write(line)
                sys.__stdout__.flush()
            except Exception:
                pass


def _emit(callback, line: str) -> None:
    if callback is None:
        try:
            sys.stdout.write(line)
            sys.stdout.flush()
        except Exception:
            pass
        return
    try:
        callback.emit(line)
    except Exception:
        pass


def _run_in_thread(workdir: str, config_path: str, callback, result: list):
    """在子线程跑 main(),结果(退出码 / 异常)塞进 result[0]"""
    project_root = Path(workdir).expanduser().resolve()
    main_py = project_root / "binance_etf_configurable.py"
    if not main_py.exists():
        _emit(callback, f"[run] 主脚本不存在: {main_py}\n")
        result.append((2, None))
        return

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

    # 强制重新加载
    for mod_name in list(sys.modules.keys()):
        if mod_name == "binance_etf_configurable" or mod_name.startswith("binance_etf_configurable."):
            del sys.modules[mod_name]

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("binance_etf_configurable", str(main_py))
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载 spec: {main_py}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["binance_etf_configurable"] = module
        spec.loader.exec_module(module)

        if config_path:
            sys.argv = ["binance_etf_configurable.py", config_path]
        else:
            sys.argv = ["binance_etf_configurable.py"]

        _emit(callback, "[run] 调用 main() ...\n")
        try:
            module.main()
            result.append((0, None))
        except SystemExit as e:
            result.append((int(e.code) if e.code is not None else 0, None))
        except BaseException as e:
            traceback.print_exc()
            result.append((1, e))
    except BaseException as e:
        traceback.print_exc()
        result.append((2, e))


def run_with_callback(workdir: str, config_path: str = "", callback=None, timeout_sec: int = 240) -> int:
    """
    在子线程跑 main(),主线程等待,超过 timeout_sec 强制超时返回 -2。
    stdout / stderr 全部转发到 callback。
    """
    project_root = Path(workdir).expanduser().resolve()
    main_py = project_root / "binance_etf_configurable.py"
    if not main_py.exists():
        _emit(callback, f"[run] 主脚本不存在: {main_py}\n")
        return 2

    # 重定向 stdout / stderr
    orig_stdout, orig_stderr = sys.stdout, sys.stderr
    cb_stream = _CallbackStream(callback, also_stdout=True)
    sys.stdout = cb_stream
    sys.stderr = cb_stream

    result: list = []
    t0 = time.time()
    try:
        _emit(callback, f"[run] 工作目录: {project_root}\n")
        _emit(callback, f"[run] Python: {sys.executable}\n")
        _emit(callback, f"[run] 超时阈值: {timeout_sec} 秒\n")

        th = threading.Thread(
            target=_run_in_thread,
            args=(workdir, config_path, callback, result),
            daemon=True,
            name="etf-monitor-main",
        )
        th.start()

        # 主线程等,带心跳
        last_heartbeat = t0
        while th.is_alive():
            th.join(timeout=2.0)
            now = time.time()
            if now - t0 > timeout_sec:
                _emit(callback, f"\n[run] 超时({timeout_sec}s),放弃等待。线程在后台继续,资源会随进程释放。\n")
                # 主线程放弃等待,后台线程 daemon=True 不会阻塞进程退出
                return -2
            if now - last_heartbeat > 10:
                elapsed = int(now - t0)
                _emit(callback, f"[run] ...已运行 {elapsed}s\n")
                last_heartbeat = now
    finally:
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        cb_stream.flush()

    if not result:
        _emit(callback, "\n[run] 异常结束: 子线程未返回结果\n")
        return -1

    rc, exc = result[0]
    elapsed = int(time.time() - t0)
    _emit(callback, f"\n[run] 完成,exit code: {rc}, 耗时: {elapsed}s\n")
    return rc