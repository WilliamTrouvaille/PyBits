"""进程执行"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from .utils import to_text, utc_now


def run_process(
    cmd: list[str],
    *,
    timeout_s: float,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> dict[str, Any]:
    """
    执行子进程并捕获输出，支持超时控制

    Args:
        cmd: 命令参数列表
        timeout_s: 超时时间（秒）
        cwd: 工作目录，None 表示使用当前目录
        env: 环境变量字典，None 表示继承当前环境
        input_text: 标准输入内容

    Returns:
        执行结果字典，包含以下字段：
        - started_at: 开始时间（ISO8601）
        - finished_at: 结束时间（ISO8601）
        - duration_ms: 执行耗时（毫秒）
        - timed_out: 是否超时
        - exit_code: 退出码（超时时为 None）
        - stdout: 标准输出
        - stderr: 标准错误输出
    """
    started_at = utc_now()
    t0 = time.perf_counter()

    try:
        proc = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
        duration_ms = round((time.perf_counter() - t0) * 1000)

        return {
            "started_at": started_at,
            "finished_at": utc_now(),
            "duration_ms": duration_ms,
            "timed_out": False,
            "exit_code": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
        }

    except subprocess.TimeoutExpired as e:
        duration_ms = round((time.perf_counter() - t0) * 1000)

        return {
            "started_at": started_at,
            "finished_at": utc_now(),
            "duration_ms": duration_ms,
            "timed_out": True,
            "exit_code": None,
            "stdout": to_text(e.stdout),
            "stderr": to_text(e.stderr),
        }


def get_version(exe: str, candidates: list[list[str]]) -> str | None:
    """
    尝试多种参数组合获取 CLI 工具的版本号

    Args:
        exe: 可执行文件路径
        candidates: 参数组合列表，例如 [["--version"], ["-v"]]

    Returns:
        版本号字符串（第一行），获取失败时返回 None
    """
    for extra in candidates:
        res = run_process([exe, *extra], timeout_s=10)
        if res["exit_code"] == 0:
            text = (res["stdout"] or res["stderr"] or "").strip()
            if text:
                return text.splitlines()[0].strip()
    return None
