"""响应规范化"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .security import redact
from .utils import parse_json_maybe, parse_jsonl, text_sha256_12


def event_type_of(obj: Any) -> str:
    """
    从事件对象中提取类型字段

    尝试多个可能的路径查找事件类型：
    - type
    - event.type
    - msg.type
    - message.type

    Args:
        obj: 事件对象

    Returns:
        事件类型字符串，找不到时返回 "unknown" 或对象类型名
    """
    if not isinstance(obj, dict):
        return type(obj).__name__

    # 尝试多个可能的路径
    for path in (
        ("type",),
        ("event", "type"),
        ("msg", "type"),
        ("message", "type"),
    ):
        cur: Any = obj
        ok = True
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                ok = False
                break
            cur = cur[key]
        if ok and isinstance(cur, str):
            return cur

    return "unknown"


def find_string_field(obj: Any, keys: set[str]) -> str | None:
    """
    递归查找对象中指定键名的字符串值

    Args:
        obj: 待搜索的对象（dict、list 或其他类型）
        keys: 目标键名集合

    Returns:
        找到的第一个非空字符串值，找不到时返回 None
    """
    if isinstance(obj, dict):
        # 先在当前层级查找
        for k, v in obj.items():
            if str(k) in keys and isinstance(v, str) and v.strip():
                return v
        # 递归查找嵌套值
        for v in obj.values():
            hit = find_string_field(v, keys)
            if hit:
                return hit

    if isinstance(obj, list):
        # 递归查找列表元素
        for v in obj:
            hit = find_string_field(v, keys)
            if hit:
                return hit

    return None


def normalize_claude_response(stdout: str) -> dict[str, Any]:
    """
    规范化 Claude Code CLI 的响应输出

    Args:
        stdout: Claude Code CLI 的标准输出

    Returns:
        规范化的响应字典，包含以下字段：
        - raw_format: 原始格式（"json" 或 "text_or_unknown"）
        - assistant_text: 助手回复文本（截断到 2000 字符）
        - assistant_text_sha256_12: 回复文本的 SHA256 前 12 位
        - metadata: 元数据字典（session_id、total_cost_usd、usage 等）
        - parsed_top_level_keys: JSON 顶层键名列表（仅 JSON 格式）
    """
    parsed = parse_json_maybe(stdout)
    response: dict[str, Any] = {
        "raw_format": "json" if isinstance(parsed, dict) else "text_or_unknown",
        "assistant_text": "",
        "assistant_text_sha256_12": None,
        "metadata": {},
    }

    if isinstance(parsed, dict):
        # JSON 格式响应
        assistant_text = parsed.get("result")
        if isinstance(assistant_text, str):
            response["assistant_text"] = assistant_text
            response["assistant_text_sha256_12"] = text_sha256_12(assistant_text)

        # 提取元数据
        for key in (
            "session_id",
            "total_cost_usd",
            "usage",
            "duration_ms",
            "duration_api_ms",
            "num_turns",
            "is_error",
            "subtype",
        ):
            if key in parsed:
                response["metadata"][key] = redact(parsed[key], key)

        response["parsed_top_level_keys"] = sorted(str(k) for k in parsed.keys())
    else:
        # 纯文本响应
        text = stdout.strip()
        response["assistant_text"] = text
        response["assistant_text_sha256_12"] = text_sha256_12(text)

    # 截断过长的文本
    if len(response["assistant_text"]) > 2000:
        response["assistant_text"] = (
            response["assistant_text"][:2000] + "...<truncated>"
        )

    return response


def normalize_codex_response(stdout: str, last_message_path: Path) -> dict[str, Any]:
    """
    规范化 Codex CLI 的响应输出

    Args:
        stdout: Codex CLI 的标准输出（JSONL 格式）
        last_message_path: 最后消息文件路径

    Returns:
        规范化的响应字典，包含以下字段：
        - raw_format: 原始格式（"jsonl"）
        - assistant_text: 助手回复文本（截断到 2000 字符）
        - assistant_text_sha256_12: 回复文本的 SHA256 前 12 位
        - event_count: 事件总数
        - bad_jsonl_line_count: 解析失败的行数
        - event_type_counts: 事件类型计数字典
        - metadata: 元数据字典（session_id、conversation_id、model 等）
    """
    events, bad_lines = parse_jsonl(stdout)

    # 统计事件类型
    event_counts: dict[str, int] = {}
    for event in events:
        typ = event_type_of(event)
        event_counts[typ] = event_counts.get(typ, 0) + 1

    # 提取助手回复文本
    assistant_text = ""
    if last_message_path.exists():
        try:
            assistant_text = last_message_path.read_text(
                encoding="utf-8", errors="replace"
            ).strip()
        except Exception:
            assistant_text = ""

    # 如果文件中没有，从事件中查找
    if not assistant_text:
        for event in reversed(events[-20:]):
            hit = find_string_field(
                event, {"final_message", "message", "content", "text", "output_text"}
            )
            if hit:
                assistant_text = hit.strip()
                break

    response: dict[str, Any] = {
        "raw_format": "jsonl",
        "assistant_text": assistant_text[:2000]
        + ("...<truncated>" if len(assistant_text) > 2000 else ""),
        "assistant_text_sha256_12": text_sha256_12(assistant_text),
        "event_count": len(events),
        "bad_jsonl_line_count": bad_lines,
        "event_type_counts": dict(sorted(event_counts.items())),
        "metadata": {},
    }

    # 提取元数据（从任意事件中，避免重复）
    for event in events:
        if not isinstance(event, dict):
            continue
        for key in (
            "session_id",
            "conversation_id",
            "model",
            "total_cost_usd",
            "usage",
        ):
            if key in event and key not in response["metadata"]:
                response["metadata"][key] = redact(event[key], key)

    return response
