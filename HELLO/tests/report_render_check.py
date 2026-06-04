"""检查 HELLO 报告渲染器的核心输出。"""

from __future__ import annotations

from typing import Any

from HELLO.src.report import build_report


def success_probe() -> dict[str, Any]:
    """
    构造包含 Claude Code 和 Codex 成功结果的最小 envelope。

    Returns:
        可传给 build_report 的探测结果字典。
    """
    return {
        "services": [
            {
                "service": "claude_code",
                "ok": True,
                "config": {
                    "observed": {
                        "model": "sonnet",
                        "alwaysThinkingEnabled": True,
                    }
                },
                "response": {"assistant_text": "hello"},
                "process": {
                    "exit_code": 0,
                    "timed_out": False,
                    "duration_ms": 123,
                },
            },
            {
                "service": "codex",
                "ok": True,
                "config": {
                    "observed": {
                        "model": "gpt-5",
                        "model_reasoning_effort": "xhigh",
                        "model_providers": [{"id": "openai"}],
                    }
                },
                "response": {"assistant_text": "hi"},
                "process": {
                    "exit_code": 0,
                    "timed_out": False,
                    "duration_ms": 456,
                },
            },
        ]
    }


def failure_probe() -> dict[str, Any]:
    """
    构造缺失 CLI 的失败结果。

    Returns:
        可传给 build_report 的探测结果字典。
    """
    return {
        "services": [
            {
                "service": "codex",
                "ok": False,
                "status": "missing_cli",
                "process": None,
            }
        ]
    }


def main() -> int:
    """
    执行报告渲染断言。

    Returns:
        进程退出码。
    """
    compact_text, compact_ok = build_report(success_probe(), compact=True)
    assert compact_ok is True
    assert "总体连通性：全部成功" in compact_text
    assert "Claude Code：连通成功" in compact_text
    assert "Codex：连通成功" in compact_text

    full_text, full_ok = build_report(failure_probe(), compact=False)
    assert full_ok is False
    assert "总体连通性：存在失败" in full_text
    assert "status：missing_cli" in full_text
    assert "请运行 HELLO --raw 查看完整输出" in full_text
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
