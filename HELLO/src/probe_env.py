"""Codex 探测环境辅助函数。"""

from __future__ import annotations

import os
from pathlib import Path

CODEX_FALLBACK_DIRS = (
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/Applications/Codex.app/Contents/Resources"),
    Path("~/Library/pnpm/bin"),
    Path("~/.local/bin"),
)


def build_codex_probe_env(
    fallback_dirs: list[Path] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """
    构造 Codex CLI 发现和子进程探测共用的环境变量。

    当前 PATH 保持最高优先级；fallback 只补充 launchd 默认 PATH
    不包含的常见 macOS 可执行文件目录。
    """
    env = os.environ.copy()
    checked_dirs = existing_dirs(fallback_dirs or list(CODEX_FALLBACK_DIRS))
    env["PATH"] = append_path(env.get("PATH", ""), checked_dirs)
    return env, [str(path) for path in checked_dirs]


def append_path(current_path: str, extra_dirs: list[Path]) -> str:
    """将 fallback 目录追加到 PATH，避免重复条目。"""
    entries = [entry for entry in current_path.split(os.pathsep) if entry]
    for path in extra_dirs:
        entry = str(path)
        if entry not in entries:
            entries.append(entry)
    return os.pathsep.join(entries)


def existing_dirs(paths: list[Path]) -> list[Path]:
    """按首次出现顺序保留实际存在的目录。"""
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        expanded = path.expanduser().resolve()
        if not expanded.is_dir():
            continue
        key = str(expanded)
        if key in seen:
            continue
        seen.add(key)
        out.append(expanded)
    return out
