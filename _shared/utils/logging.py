"""Shared loguru setup for PyBits tools."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from loguru import logger


def setup_tool_logger(
    tool_name: str,
    logs_dir: Path | str | None = None,
    verbose: bool = False,
    retention_days: int = 30,
    console_level: str | None = None,
) -> None:
    """Configure console and rotating file logging for a PyBits tool."""
    normalized_name = _normalize_tool_name(tool_name)
    resolved_logs_dir = Path(logs_dir) if logs_dir else Path.cwd() / "logs"
    resolved_logs_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stderr,
        level=console_level or ("INFO" if verbose else "WARNING"),
        format="<level>{level: <8}</level> | <level>{message}</level>",
    )
    logger.add(
        resolved_logs_dir / f"{normalized_name}_{{time:YYYY-MM-DD}}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",
        retention=f"{retention_days} days",
        encoding="utf-8",
    )


def _normalize_tool_name(tool_name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", tool_name.strip().lower())
    return normalized.strip("_") or "pybits"
