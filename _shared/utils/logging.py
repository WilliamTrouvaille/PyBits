"""Shared loguru setup for PyBits tools."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from loguru import logger

from .trash import soft_delete


def setup_tool_logger(
    tool_name: str,
    logs_dir: Path | str | None = None,
    verbose: bool = False,
    retention_days: int = 30,
    console_level: str | None = None,
) -> None:
    """Configure console and rotating file logging for a PyBits tool."""
    normalized_name = _normalize_tool_name(tool_name)
    log_file_name = f"{normalized_name}_{{time:YYYY-MM-DD}}.log"

    logger.remove()
    logger.add(
        sys.stderr,
        level=console_level or ("INFO" if verbose else "WARNING"),
        format="<level>{level: <8}</level> | <level>{message}</level>",
    )

    for candidate_dir in _candidate_logs_dirs(tool_name, logs_dir):
        try:
            candidate_dir.mkdir(parents=True, exist_ok=True)
            _soft_delete_old_logs(candidate_dir, normalized_name, retention_days)
            logger.add(
                candidate_dir / log_file_name,
                level="DEBUG",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
                rotation="00:00",
                encoding="utf-8",
            )
            return
        except OSError:
            continue

    raise RuntimeError(f"No writable log directory found for {tool_name}")


def _normalize_tool_name(tool_name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", tool_name.strip().lower())
    return normalized.strip("_") or "pybits"


def _candidate_logs_dirs(tool_name: str, logs_dir: Path | str | None) -> list[Path]:
    candidates: list[Path] = []

    origin_dir = _install_origin()
    if origin_dir:
        candidates.append(origin_dir / tool_name.strip().upper() / "logs")

    if logs_dir:
        candidates.append(Path(logs_dir))

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        expanded = candidate.expanduser()
        if expanded not in seen:
            unique_candidates.append(expanded)
            seen.add(expanded)
    return unique_candidates


def _install_origin() -> Path | None:
    try:
        distribution = importlib_metadata.distribution("pybits")
    except importlib_metadata.PackageNotFoundError:
        return None

    direct_url_text = distribution.read_text("direct_url.json")
    if not direct_url_text:
        return None

    try:
        direct_url_data = json.loads(direct_url_text)
    except json.JSONDecodeError:
        return None

    url = direct_url_data.get("url")
    if not isinstance(url, str):
        return None

    parsed_url = urlparse(url)
    if parsed_url.scheme != "file":
        return None

    return Path(unquote(parsed_url.path)).expanduser().resolve()


def _soft_delete_old_logs(logs_dir: Path, normalized_name: str, retention_days: int) -> None:
    if retention_days <= 0:
        return

    cutoff = datetime.now() - timedelta(days=retention_days)
    for log_file in logs_dir.glob(f"{normalized_name}_*.log"):
        try:
            if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff:
                soft_delete(log_file, f"{normalized_name}-old-log")
        except OSError:
            continue
