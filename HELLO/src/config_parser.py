"""配置文件解析"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .security import collect_header_sources, redact
from .utils import sha256_12


def load_json_file(path: Path) -> tuple[Any | None, str | None]:
    """
    加载 JSON 文件

    Args:
        path: 文件路径

    Returns:
        元组 (解析后的对象, 错误信息)，文件不存在时返回 (None, None)
    """
    if not path.exists():
        return None, None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def load_toml_file(path: Path) -> tuple[Any | None, str | None]:
    """
    加载 TOML 文件

    Args:
        path: 文件路径

    Returns:
        元组 (解析后的对象, 错误信息)，文件不存在时返回 (None, None)
    """
    if not path.exists():
        return None, None
    try:
        with path.open("rb") as f:
            return tomllib.load(f), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def host_only(url: Any) -> str | None:
    """
    从 URL 中提取主机名部分

    Args:
        url: URL 字符串

    Returns:
        主机名，解析失败时返回原 URL 或 None
    """
    if not isinstance(url, str) or not url:
        return None
    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc
    return url


def summarize_claude_settings(parsed: Any) -> dict[str, Any]:
    """
    提取 Claude Code 配置文件的关键信息摘要

    Args:
        parsed: 解析后的配置对象

    Returns:
        配置摘要字典，包含 model、effortLevel、alwaysThinkingEnabled、
        apiKeyHelper_present、env_keys、anthropic_route_env_keys、permissions 等字段
    """
    if not isinstance(parsed, dict):
        return {}

    env = parsed.get("env")
    permissions = parsed.get("permissions")

    summary: dict[str, Any] = {}

    # 提取关键配置字段
    for key in ("model", "effortLevel", "alwaysThinkingEnabled"):
        if key in parsed:
            summary[key] = redact(parsed[key], key)

    summary["apiKeyHelper_present"] = bool(parsed.get("apiKeyHelper"))

    # 提取环境变量键名
    if isinstance(env, dict):
        summary["env_keys"] = sorted(str(k) for k in env)
        summary["anthropic_route_env_keys"] = sorted(
            str(k)
            for k in env
            if str(k).startswith("ANTHROPIC_") or str(k).startswith("CLAUDE_CODE_")
        )

    # 提取权限配置统计
    if isinstance(permissions, dict):
        summary["permissions"] = {
            "allow_count": len(permissions.get("allow", []) or []),
            "ask_count": len(permissions.get("ask", []) or []),
            "deny_count": len(permissions.get("deny", []) or []),
        }

    return summary


def summarize_codex_config(parsed: Any) -> dict[str, Any]:
    """
    提取 Codex 配置文件的关键信息摘要

    Args:
        parsed: 解析后的配置对象

    Returns:
        配置摘要字典，包含 model、model_provider、approval_policy、
        sandbox_mode、model_reasoning_effort、model_providers 等字段
    """
    if not isinstance(parsed, dict):
        return {}

    summary: dict[str, Any] = {}

    # 提取关键配置字段
    for key in (
        "model",
        "model_provider",
        "approval_policy",
        "sandbox_mode",
        "model_reasoning_effort",
        "model_reasoning_summary",
    ):
        if key in parsed:
            summary[key] = redact(parsed[key], key)

    # 提取 model_providers 配置
    providers = parsed.get("model_providers")
    if isinstance(providers, dict):
        provider_summaries = []
        for provider_id, cfg in providers.items():
            item: dict[str, Any] = {"id": str(provider_id)}
            if isinstance(cfg, dict):
                if "name" in cfg:
                    item["name"] = redact(cfg["name"], "name")
                if "base_url" in cfg:
                    item["base_url_host"] = host_only(cfg.get("base_url"))
                if "env_key" in cfg:
                    item["env_key"] = redact(cfg["env_key"], "env_key")
                if "requires_openai_auth" in cfg:
                    item["requires_openai_auth"] = bool(cfg.get("requires_openai_auth"))
                if "experimental_bearer_token" in cfg:
                    item["experimental_bearer_token_present"] = bool(
                        cfg.get("experimental_bearer_token")
                    )
                if isinstance(cfg.get("http_headers"), dict):
                    item["http_header_keys"] = sorted(str(k) for k in cfg["http_headers"])
                if isinstance(cfg.get("env_http_headers"), dict):
                    item["env_http_header_keys"] = sorted(str(k) for k in cfg["env_http_headers"])
            provider_summaries.append(item)

        summary["model_providers"] = provider_summaries

    return summary


def config_summary(kind: str, path: Path) -> dict[str, Any]:
    """
    生成配置文件的完整摘要

    Args:
        kind: 配置类型，"claude" 或 "codex"
        path: 配置文件路径

    Returns:
        配置摘要字典，包含文件存在性、大小、哈希、解析状态、
        顶层键名、header 源、以及特定于配置类型的观察字段
    """
    exists = path.exists() and path.is_file()
    info: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
    }

    if not exists:
        return info

    # 文件元信息
    info["size_bytes"] = path.stat().st_size
    info["sha256_12"] = sha256_12(path)

    # 解析配置文件
    if kind == "claude":
        parsed, parse_error = load_json_file(path)
    elif kind == "codex":
        parsed, parse_error = load_toml_file(path)
    else:
        parsed, parse_error = None, "unknown config kind"

    info["parse_ok"] = parse_error is None
    if parse_error:
        info["parse_error"] = parse_error
        return info

    # 提取顶层键名
    if isinstance(parsed, dict):
        info["top_level_keys"] = sorted(str(k) for k in parsed)

    # 收集 header 源
    info["header_sources"] = collect_header_sources(parsed)

    # 生成特定于配置类型的摘要
    if kind == "claude":
        info["observed"] = summarize_claude_settings(parsed)
    elif kind == "codex":
        info["observed"] = summarize_codex_config(parsed)

    return info
