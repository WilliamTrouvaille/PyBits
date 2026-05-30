"""
HELLO 命令行入口。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from loguru import logger

from _shared.utils.logging import setup_tool_logger

from .src.cli_parser import SERVICE_ALIASES, build_parser
from .src.cli_runtime import execute_probe, print_result, resolve_services

LOGS_DIR = Path(__file__).parent / "logs"


def main() -> int:
    """
    解析参数、执行服务探测并输出探测报告。

    Returns:
        进程退出码，0 表示请求的服务探测均通过或用户要求始终返回 0。
    """
    parser = build_parser()
    args = parser.parse_args()

    setup_tool_logger(
        "hello",
        logs_dir=LOGS_DIR,
        verbose=args.verbose,
        retention_days=7,
    )
    logger.info("HELLO 探测工具启动")

    try:
        services = resolve_services(args, SERVICE_ALIASES)
    except ValueError as exc:
        parser.error(str(exc))
    logger.info(f"探测服务: {services}")

    with tempfile.TemporaryDirectory(prefix="hello-probe-", ignore_cleanup_errors=True) as td:
        workdir = Path(td)
        envelope = execute_probe(args, services, workdir)

    exit_code = print_result(envelope, args)
    logger.info(f"探测完成，退出码: {exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
