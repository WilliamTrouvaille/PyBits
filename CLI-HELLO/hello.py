#!/usr/bin/env -S uv run --script
# requires-python = ">=3.12"
# dependencies = []


from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "ai-cli-connectivity-probe/v1"
DEFAULT_PROMPT = "hello？"

SECRET_KEY_HINTS = (
    "key",
    "token",
    "secret",
    "password",
    "credential",
    "authorization",
    "bearer",
    "cookie",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def expand_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def tail_text(text: str, limit: int = 4000) -> str:
    text = strip_ansi(text or "")
    if len(text) <= limit:
        return text
    return text[-limit:]


def sha256_12(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def text_sha256_12(text: str) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def command_display(cmd: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in SECRET_KEY_HINTS)


def redact(obj: Any, parent_key: str = "") -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            key = str(k)
            if is_sensitive_key(key):
                out[key] = "<redacted>"
            else:
                out[key] = redact(v, key)
        return out

    if isinstance(obj, list):
        return [redact(v, parent_key) for v in obj]

    if isinstance(obj, str):
        if is_sensitive_key(parent_key):
            return "<redacted>"
        if len(obj) > 300:
            return obj[:200] + "...<truncated>"
        return obj

    return obj


def parse_json_maybe(text: str) -> Any | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_jsonl(text: str) -> tuple[list[Any], int]:
    events: list[Any] = []
    bad_lines = 0

    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            bad_lines += 1

    return events, bad_lines


def run_process(
    cmd: list[str],
    *,
    timeout_s: float,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> dict[str, Any]:
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


def load_json_file(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def load_toml_file(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, None
    try:
        with path.open("rb") as f:
            return tomllib.load(f), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def parse_header_names_from_string(value: str) -> list[str]:
    names: list[str] = []
    for line in value.splitlines():
        if ":" in line:
            name = line.split(":", 1)[0].strip()
            if name:
                names.append(name)
    return sorted(set(names))


def collect_header_sources(obj: Any, prefix: str = "") -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            path = f"{prefix}.{key}" if prefix else key
            lowered = key.lower()

            if "headers" in lowered:
                if isinstance(v, dict):
                    found.append(
                        {
                            "path": path,
                            "kind": "map",
                            "keys": sorted(str(x) for x in v.keys()),
                            "values_redacted": True,
                        }
                    )
                elif isinstance(v, str):
                    found.append(
                        {
                            "path": path,
                            "kind": "string",
                            "keys": parse_header_names_from_string(v),
                            "values_redacted": True,
                        }
                    )
                else:
                    found.append(
                        {
                            "path": path,
                            "kind": type(v).__name__,
                            "keys": [],
                            "values_redacted": True,
                        }
                    )

            found.extend(collect_header_sources(v, path))

    elif isinstance(obj, list):
        for idx, v in enumerate(obj):
            found.extend(collect_header_sources(v, f"{prefix}[{idx}]"))

    return found


def host_only(url: Any) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc
    return url


def summarize_claude_settings(parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}

    env = parsed.get("env")
    permissions = parsed.get("permissions")

    summary: dict[str, Any] = {}

    for key in ("model", "effortLevel", "alwaysThinkingEnabled"):
        if key in parsed:
            summary[key] = redact(parsed[key], key)

    summary["apiKeyHelper_present"] = bool(parsed.get("apiKeyHelper"))

    if isinstance(env, dict):
        summary["env_keys"] = sorted(str(k) for k in env.keys())
        summary["anthropic_route_env_keys"] = sorted(
            str(k)
            for k in env.keys()
            if str(k).startswith("ANTHROPIC_") or str(k).startswith("CLAUDE_CODE_")
        )

    if isinstance(permissions, dict):
        summary["permissions"] = {
            "allow_count": len(permissions.get("allow", []) or []),
            "ask_count": len(permissions.get("ask", []) or []),
            "deny_count": len(permissions.get("deny", []) or []),
        }

    return summary


def summarize_codex_config(parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}

    summary: dict[str, Any] = {}

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
                    item["experimental_bearer_token_present"] = bool(cfg.get("experimental_bearer_token"))
                if isinstance(cfg.get("http_headers"), dict):
                    item["http_header_keys"] = sorted(str(k) for k in cfg["http_headers"].keys())
                if isinstance(cfg.get("env_http_headers"), dict):
                    item["env_http_header_keys"] = sorted(str(k) for k in cfg["env_http_headers"].keys())
            provider_summaries.append(item)

        summary["model_providers"] = provider_summaries

    return summary


def config_summary(kind: str, path: Path) -> dict[str, Any]:
    exists = path.exists() and path.is_file()
    info: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
    }

    if not exists:
        return info

    info["size_bytes"] = path.stat().st_size
    info["sha256_12"] = sha256_12(path)

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

    if isinstance(parsed, dict):
        info["top_level_keys"] = sorted(str(k) for k in parsed.keys())

    info["header_sources"] = collect_header_sources(parsed)

    if kind == "claude":
        info["observed"] = summarize_claude_settings(parsed)
    elif kind == "codex":
        info["observed"] = summarize_codex_config(parsed)

    return info


def get_version(exe: str, candidates: list[list[str]]) -> str | None:
    for extra in candidates:
        res = run_process([exe, *extra], timeout_s=10)
        if res["exit_code"] == 0:
            text = (res["stdout"] or res["stderr"] or "").strip()
            if text:
                return text.splitlines()[0].strip()
    return None


def summarize_auth_check(name: str, res: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_json_maybe(res["stdout"])

    summary: dict[str, Any] = {
        "checked": True,
        "ok": res["exit_code"] == 0 and not res["timed_out"],
        "exit_code": res["exit_code"],
        "duration_ms": res["duration_ms"],
        "timed_out": res["timed_out"],
    }

    if parsed is not None:
        summary["parsed"] = redact(parsed)
    else:
        summary["stdout_tail"] = tail_text(res["stdout"], 1000)
        summary["stderr_tail"] = tail_text(res["stderr"], 1000)

    return summary


def missing_cli_result(service: str, binary_name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "service": service,
        "ok": False,
        "status": "missing_cli",
        "cli": {
            "binary": binary_name,
            "path": None,
            "version": None,
        },
        "config": cfg,
        "auth": {
            "checked": False,
            "ok": None,
            "reason": "cli_not_found",
        },
        "request": None,
        "response": None,
        "process": None,
        "warnings": [
            f"Cannot find `{binary_name}` in PATH.",
        ],
    }


def normalize_claude_response(stdout: str) -> dict[str, Any]:
    parsed = parse_json_maybe(stdout)
    response: dict[str, Any] = {
        "raw_format": "json" if isinstance(parsed, dict) else "text_or_unknown",
        "assistant_text": "",
        "assistant_text_sha256_12": None,
        "metadata": {},
    }

    if isinstance(parsed, dict):
        assistant_text = parsed.get("result")
        if isinstance(assistant_text, str):
            response["assistant_text"] = assistant_text
            response["assistant_text_sha256_12"] = text_sha256_12(assistant_text)

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
        text = stdout.strip()
        response["assistant_text"] = text
        response["assistant_text_sha256_12"] = text_sha256_12(text)

    if len(response["assistant_text"]) > 2000:
        response["assistant_text"] = response["assistant_text"][:2000] + "...<truncated>"

    return response


def event_type_of(obj: Any) -> str:
    if not isinstance(obj, dict):
        return type(obj).__name__

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
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k) in keys and isinstance(v, str) and v.strip():
                return v
        for v in obj.values():
            hit = find_string_field(v, keys)
            if hit:
                return hit

    if isinstance(obj, list):
        for v in obj:
            hit = find_string_field(v, keys)
            if hit:
                return hit

    return None


def normalize_codex_response(stdout: str, last_message_path: Path) -> dict[str, Any]:
    events, bad_lines = parse_jsonl(stdout)

    event_counts: dict[str, int] = {}
    for event in events:
        typ = event_type_of(event)
        event_counts[typ] = event_counts.get(typ, 0) + 1

    assistant_text = ""
    if last_message_path.exists():
        try:
            assistant_text = last_message_path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            assistant_text = ""

    if not assistant_text:
        for event in reversed(events[-20:]):
            hit = find_string_field(event, {"final_message", "message", "content", "text", "output_text"})
            if hit:
                assistant_text = hit.strip()
                break

    response: dict[str, Any] = {
        "raw_format": "jsonl",
        "assistant_text": assistant_text[:2000] + ("...<truncated>" if len(assistant_text) > 2000 else ""),
        "assistant_text_sha256_12": text_sha256_12(assistant_text),
        "event_count": len(events),
        "bad_jsonl_line_count": bad_lines,
        "event_type_counts": dict(sorted(event_counts.items())),
        "metadata": {},
    }

    for event in events:
        if not isinstance(event, dict):
            continue
        for key in ("session_id", "conversation_id", "model", "total_cost_usd", "usage"):
            if key in event and key not in response["metadata"]:
                response["metadata"][key] = redact(event[key], key)

    return response


def probe_claude(args: argparse.Namespace, workdir: Path) -> dict[str, Any]:
    service_started_at = utc_now()

    cfg_path = expand_path(args.claude_settings)
    cfg = config_summary("claude", cfg_path)

    exe = shutil.which(args.claude_bin)
    if not exe:
        return missing_cli_result("claude_code", args.claude_bin, cfg)

    version = get_version(exe, [["--version"], ["-v"]])

    auth = {"checked": False, "ok": None}
    if not args.skip_auth_check:
        auth_res = run_process([exe, "auth", "status"], timeout_s=min(args.timeout, 30), cwd=workdir)
        auth = summarize_auth_check("claude", auth_res)

    cmd = [
        exe,
        "-p",
        args.prompt,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--max-turns",
        "1",
        "--tools",
        "",
    ]

    if args.claude_setting_sources:
        cmd.extend(["--setting-sources", args.claude_setting_sources])

    if cfg_path.exists():
        cmd.extend(["--settings", str(cfg_path)])

    warnings: list[str] = []
    if not cfg_path.exists():
        warnings.append(f"Claude settings file does not exist: {cfg_path}")

    proc = run_process(cmd, timeout_s=args.timeout, cwd=workdir)
    response = normalize_claude_response(proc["stdout"])

    ok = proc["exit_code"] == 0 and not proc["timed_out"]

    return {
        "service": "claude_code",
        "ok": ok,
        "status": "pass" if ok else ("timeout" if proc["timed_out"] else "failed"),
        "started_at": service_started_at,
        "finished_at": utc_now(),
        "cli": {
            "binary": args.claude_bin,
            "path": exe,
            "version": version,
        },
        "config": cfg,
        "auth": auth,
        "request": {
            "message": args.prompt,
            "transport": "official_cli",
            "header_handling": "delegated_to_claude_code_cli",
            "observable_header_sources": cfg.get("header_sources", []),
        },
        "response": response,
        "process": {
            "command": command_display(cmd),
            "exit_code": proc["exit_code"],
            "timed_out": proc["timed_out"],
            "duration_ms": proc["duration_ms"],
            "stdout_bytes": len(proc["stdout"].encode("utf-8", errors="replace")),
            "stderr_bytes": len(proc["stderr"].encode("utf-8", errors="replace")),
            "stderr_tail": tail_text(proc["stderr"], args.tail_chars),
            **({"stdout_raw": proc["stdout"], "stderr_raw": proc["stderr"]} if args.include_raw else {}),
        },
        "warnings": warnings,
    }


def probe_codex(args: argparse.Namespace, base_workdir: Path) -> dict[str, Any]:
    service_started_at = utc_now()

    codex_home = expand_path(args.codex_home) if args.codex_home else None
    cfg_path = expand_path(args.codex_config) if args.codex_config else (
        codex_home / "config.toml" if codex_home else expand_path("~/.codex/config.toml")
    )

    cfg = config_summary("codex", cfg_path)

    exe = shutil.which(args.codex_bin)
    if not exe:
        return missing_cli_result("codex", args.codex_bin, cfg)

    version = get_version(exe, [["--version"], ["-V"]])

    env = os.environ.copy()
    if codex_home:
        env["CODEX_HOME"] = str(codex_home)

    warnings: list[str] = []
    if not cfg_path.exists():
        warnings.append(f"Codex config file does not exist: {cfg_path}")

    if args.codex_config and codex_home:
        expected = codex_home / "config.toml"
        if cfg_path != expected:
            warnings.append(
                "A custom --codex-config is inspected by this script, but Codex CLI loads config from CODEX_HOME/config.toml. "
                f"Current CODEX_HOME/config.toml is: {expected}"
            )

    auth = {"checked": False, "ok": None}
    if not args.skip_auth_check:
        auth_res = run_process([exe, "login", "status"], timeout_s=min(args.timeout, 30), cwd=base_workdir, env=env)
        auth = summarize_auth_check("codex", auth_res)

    with tempfile.TemporaryDirectory(prefix="codex-hello-probe-") as td:
        temp_dir = Path(td)
        last_message_path = temp_dir / "last_message.txt"
        codex_cd = expand_path(args.codex_cd) if args.codex_cd else temp_dir

        cmd = [
            exe,
            "exec",
            "--json",
            "--color",
            "never",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--output-last-message",
            str(last_message_path),
            "--cd",
            str(codex_cd),
        ]

        if args.codex_profile:
            cmd.extend(["--profile", args.codex_profile])

        cmd.append(args.prompt)

        proc = run_process(cmd, timeout_s=args.timeout, cwd=codex_cd, env=env)
        response = normalize_codex_response(proc["stdout"], last_message_path)

    ok = proc["exit_code"] == 0 and not proc["timed_out"]

    return {
        "service": "codex",
        "ok": ok,
        "status": "pass" if ok else ("timeout" if proc["timed_out"] else "failed"),
        "started_at": service_started_at,
        "finished_at": utc_now(),
        "cli": {
            "binary": args.codex_bin,
            "path": exe,
            "version": version,
        },
        "config": cfg,
        "auth": auth,
        "request": {
            "message": args.prompt,
            "transport": "official_cli",
            "header_handling": "delegated_to_codex_cli",
            "observable_header_sources": cfg.get("header_sources", []),
        },
        "response": response,
        "process": {
            "command": command_display(cmd),
            "exit_code": proc["exit_code"],
            "timed_out": proc["timed_out"],
            "duration_ms": proc["duration_ms"],
            "stdout_bytes": len(proc["stdout"].encode("utf-8", errors="replace")),
            "stderr_bytes": len(proc["stderr"].encode("utf-8", errors="replace")),
            "stdout_tail": tail_text(proc["stdout"], args.tail_chars),
            "stderr_tail": tail_text(proc["stderr"], args.tail_chars),
            **({"stdout_raw": proc["stdout"], "stderr_raw": proc["stderr"]} if args.include_raw else {}),
        },
        "warnings": warnings,
    }


def expand_services(values: list[str] | None) -> list[str]:
    if not values or "all" in values:
        return ["claude", "codex"]

    out: list[str] = []
    for value in values:
        if value in ("claude", "cc", "claude_code"):
            if "claude" not in out:
                out.append("claude")
        elif value == "codex":
            if "codex" not in out:
                out.append("codex")

    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Probe Claude Code and Codex CLI connectivity with a fixed hello prompt, then emit normalized JSON.",
    )

    p.add_argument(
        "-s",
        "--service",
        action="append",
        choices=["all", "claude", "cc", "claude_code", "codex"],
        help="Service to test. Can be repeated. Default: all.",
    )
    p.add_argument("--prompt", default=DEFAULT_PROMPT, help=f"Probe prompt. Default: {DEFAULT_PROMPT!r}")
    p.add_argument("--timeout", type=float, default=120.0, help="Timeout per service call, in seconds. Default: 120.")
    p.add_argument("--parallel", action="store_true", help="Run selected probes concurrently. Default: sequential.")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    p.add_argument("--jsonl", action="store_true", help="Emit one normalized JSON object per service.")
    p.add_argument("--include-raw", action="store_true", help="Include raw stdout/stderr. Avoid in normal logs.")
    p.add_argument("--tail-chars", type=int, default=4000, help="Tail length for stdout/stderr snippets.")
    p.add_argument("--always-exit-zero", action="store_true", help="Always exit with code 0 after printing JSON.")
    p.add_argument("--skip-auth-check", action="store_true", help="Skip `claude auth status` and `codex login status`.")

    p.add_argument("--claude-bin", default="claude", help="Claude Code executable name/path. Default: claude.")
    p.add_argument(
        "--claude-settings",
        default="~/.claude/settings.json",
        help="Claude Code settings.json to inspect and pass via --settings when it exists.",
    )
    p.add_argument(
        "--claude-setting-sources",
        default="user",
        help="Value passed to Claude --setting-sources. Default: user. Use user,project,local if needed.",
    )

    p.add_argument("--codex-bin", default="codex", help="Codex executable name/path. Default: codex.")
    p.add_argument(
        "--codex-home",
        default=None,
        help="Optional CODEX_HOME. Codex normally loads config.toml from CODEX_HOME/config.toml.",
    )
    p.add_argument(
        "--codex-config",
        default=None,
        help="Codex config.toml path to inspect. If omitted, uses CODEX_HOME/config.toml or ~/.codex/config.toml.",
    )
    p.add_argument("--codex-profile", default=None, help="Optional Codex profile name passed via --profile.")
    p.add_argument("--codex-cd", default=None, help="Optional working directory passed to codex exec --cd.")

    return p


def main() -> int:
    args = build_parser().parse_args()
    services = expand_services(args.service)

    run_started_at = utc_now()

    with tempfile.TemporaryDirectory(prefix="ai-cli-hello-probe-") as td:
        workdir = Path(td)

        probe_map = {
            "claude": lambda: probe_claude(args, workdir),
            "codex": lambda: probe_codex(args, workdir),
        }

        if args.parallel and len(services) > 1:
            results: list[dict[str, Any]] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(services)) as executor:
                future_to_service = {executor.submit(probe_map[s]): s for s in services}
                for future in concurrent.futures.as_completed(future_to_service):
                    results.append(future.result())
            results.sort(key=lambda x: services.index("claude" if x["service"] == "claude_code" else x["service"]))
        else:
            results = [probe_map[s]() for s in services]

    ok = all(item.get("ok") is True for item in results)

    envelope = {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "status": "pass" if ok else "failed",
        "started_at": run_started_at,
        "finished_at": utc_now(),
        "prompt": args.prompt,
        "host": {
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "executable": sys.executable,
            "cwd": str(Path.cwd()),
        },
        "services": results,
    }

    if args.jsonl:
        for item in results:
            print(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
    else:
        if args.pretty:
            print(json.dumps(envelope, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))

    if args.always_exit_zero:
        return 0

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
