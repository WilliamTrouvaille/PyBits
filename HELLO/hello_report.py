#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_probe_json(path: str) -> tuple[dict[str, Any] | None, str | None]:
    if path == "-":
        text = sys.stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"无法解析 hello.py 输出为 JSON：{e}"

    if not isinstance(data, dict):
        return (
            None,
            f"hello.py 输出的 JSON 根对象不是 object，而是 {type(data).__name__}",
        )

    return data, None


def service_key(raw_name: Any) -> str:
    name = str(raw_name or "").lower()

    if name in {"claude_code", "claude", "cc"}:
        return "cc"

    if name == "codex":
        return "codex"

    return name or "unknown"


def service_display_name(key: str) -> str:
    if key == "cc":
        return "Claude Code"
    if key == "codex":
        return "Codex"
    return key


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def get_path(obj: Any, path: str, default: Any = None) -> Any:
    cur = obj

    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default

    return cur


def fmt_value(value: Any, missing: str = "未读取到") -> str:
    if value is None:
        return missing

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, str):
        return value if value.strip() else missing

    return json.dumps(value, ensure_ascii=False)


def hello_request_ok(service: dict[str, Any]) -> bool:
    process = as_dict(service.get("process"))

    return (
        service.get("ok") is True
        and process.get("exit_code") == 0
        and process.get("timed_out") is False
    )


def duration_ms(service: dict[str, Any]) -> str:
    value = get_path(service, "process.duration_ms")
    return fmt_value(value, "未知")


def exit_code(service: dict[str, Any]) -> str:
    value = get_path(service, "process.exit_code")
    return fmt_value(value, "未知")


def timed_out(service: dict[str, Any]) -> str:
    value = get_path(service, "process.timed_out")
    return fmt_value(value, "未知")


def response_preview(service: dict[str, Any]) -> str:
    text = get_path(service, "response.assistant_text")

    if not isinstance(text, str) or not text.strip():
        return "未读取到返回文本"

    text = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(line.strip() for line in text.splitlines() if line.strip())

    if len(text) > 120:
        return text[:120] + "..."

    return text


def render_provider(provider: dict[str, Any]) -> str:
    parts: list[str] = []

    provider_id = provider.get("id")
    name = provider.get("name")
    base_url_host = provider.get("base_url_host")
    env_key = provider.get("env_key")
    requires_openai_auth = provider.get("requires_openai_auth")
    http_header_keys = provider.get("http_header_keys")
    env_http_header_keys = provider.get("env_http_header_keys")

    if provider_id:
        parts.append(f"id={provider_id}")

    if name:
        parts.append(f"name={name}")

    if base_url_host:
        parts.append(f"base_url_host={base_url_host}")

    if env_key:
        parts.append(f"env_key={env_key}")

    if requires_openai_auth is not None:
        parts.append(f"requires_openai_auth={fmt_value(requires_openai_auth)}")

    if isinstance(http_header_keys, list) and http_header_keys:
        parts.append(
            "http_headers=[" + ", ".join(str(x) for x in http_header_keys) + "]"
        )

    if isinstance(env_http_header_keys, list) and env_http_header_keys:
        parts.append(
            "env_http_headers=[" + ", ".join(str(x) for x in env_http_header_keys) + "]"
        )

    return "；".join(parts) if parts else "未读取到 provider 细节"


def render_cc_success(service: dict[str, Any], compact: bool) -> list[str]:
    observed = as_dict(get_path(service, "config.observed", {}))

    model = fmt_value(observed.get("model"))
    always_thinking = fmt_value(observed.get("alwaysThinkingEnabled"))
    effort_level = observed.get("effortLevel")

    if compact:
        return [
            f"Claude Code：连通成功；使用的模型：{model}；alwaysThinkingEnabled：{always_thinking}；耗时：{duration_ms(service)} ms"
        ]

    lines = [
        "Claude Code：",
        "  连通性判定：连通成功！",
        f"  使用的模型：{model}",
        f"  alwaysThinkingEnabled：{always_thinking}",
    ]

    if effort_level is not None:
        lines.append(f"  effortLevel：{fmt_value(effort_level)}")

    lines.extend(
        [
            f"  请求耗时：{duration_ms(service)} ms",
            f"  返回摘要：{response_preview(service)}",
        ]
    )

    return lines


def render_codex_success(service: dict[str, Any], compact: bool) -> list[str]:
    observed = as_dict(get_path(service, "config.observed", {}))

    model = fmt_value(observed.get("model"))
    reasoning_effort = fmt_value(observed.get("model_reasoning_effort"))
    model_provider = observed.get("model_provider")
    providers = as_list(observed.get("model_providers"))

    if compact:
        provider_count = len(providers)
        return [
            f"Codex：连通成功；使用的模型：{model}；model_reasoning_effort：{reasoning_effort}；model_providers：{provider_count} 个；耗时：{duration_ms(service)} ms"
        ]

    lines = [
        "Codex：",
        "  连通性判定：连通成功！",
        f"  使用的模型：{model}",
        f"  model_reasoning_effort：{reasoning_effort}",
    ]

    if model_provider is not None:
        lines.append(f"  model_provider：{fmt_value(model_provider)}")

    lines.append("  model_providers：")

    if providers:
        for item in providers:
            if isinstance(item, dict):
                lines.append(f"    - {render_provider(item)}")
            else:
                lines.append(f"    - {fmt_value(item)}")
    else:
        lines.append("    - 未在 config.toml 中读取到 model_providers")

    lines.extend(
        [
            f"  请求耗时：{duration_ms(service)} ms",
            f"  返回摘要：{response_preview(service)}",
        ]
    )

    return lines


def render_failure(service: dict[str, Any], key: str, compact: bool) -> list[str]:
    name = service_display_name(key)
    status = fmt_value(service.get("status"), "未知")

    if compact:
        return [
            f"{name}：连通失败；status={status}；exit_code={exit_code(service)}；timed_out={timed_out(service)}；请运行 HELLO --raw 查看完整输出"
        ]

    return [
        f"{name}：",
        "  连通性判定：连通失败。",
        "  失败判断：hello 请求没有成功完成。",
        f"  status：{status}",
        f"  exit_code：{exit_code(service)}",
        f"  timed_out：{timed_out(service)}",
        f"  请求耗时：{duration_ms(service)} ms",
        "  排查方式：请运行 HELLO --raw 查看完整输出。",
    ]


def render_service(service: dict[str, Any], compact: bool) -> tuple[list[str], bool]:
    key = service_key(service.get("service"))
    ok = hello_request_ok(service)

    if not ok:
        return render_failure(service, key, compact), False

    if key == "cc":
        return render_cc_success(service, compact), True

    if key == "codex":
        return render_codex_success(service, compact), True

    name = service_display_name(key)
    return [f"{name}：连通成功；耗时：{duration_ms(service)} ms"], True


def build_report(probe: dict[str, Any], compact: bool) -> tuple[str, bool]:
    raw_services = probe.get("services")
    services = raw_services if isinstance(raw_services, list) else []

    lines: list[str] = []
    service_results: list[bool] = []

    for index, service in enumerate(services):
        if not isinstance(service, dict):
            continue

        service_lines, ok = render_service(service, compact)
        service_results.append(ok)

        if lines and not compact:
            lines.append("")

        lines.extend(service_lines)

    overall_ok = bool(service_results) and all(service_results)

    if compact:
        prefix = "总体连通性：全部成功" if overall_ok else "总体连通性：存在失败"
        return prefix + "\n" + "\n".join(lines), overall_ok

    header = "总体连通性：全部成功" if overall_ok else "总体连通性：存在失败"
    body = (
        "\n".join(lines)
        if lines
        else "没有读取到任何 service 结果。请运行 HELLO --raw 查看完整输出。"
    )

    return header + "\n\n" + body, overall_ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        "-i",
        default="-",
        help="hello.py 输出的 JSON 文件路径；默认从 stdin 读取",
    )
    parser.add_argument("--compact", action="store_true", help="输出更短的人类可读结果")
    args = parser.parse_args()

    probe, error = load_probe_json(args.input)

    if error is not None or probe is None:
        print("总体连通性：存在失败")
        print()
        print("hello.py 输出解析失败。")
        print(f"原因：{error}")
        print("排查方式：请运行 HELLO --raw 查看完整输出。")
        return 1

    text, ok = build_report(probe, args.compact)
    print(text)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
