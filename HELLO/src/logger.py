"""日志配置"""

from pathlib import Path

from _shared.utils.logging import setup_tool_logger

# 日志目录：HELLO/logs/
LOGS_DIR = Path(__file__).parent.parent / "logs"


def setup_logger(verbose: bool = False) -> None:
    """
    初始化 loguru 日志

    Args:
        verbose: 是否启用详细模式（控制台输出 INFO 级别）
    """
    setup_tool_logger(
        "hello",
        logs_dir=LOGS_DIR,
        verbose=verbose,
        retention_days=7,
    )
