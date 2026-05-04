"""日志配置"""

import sys
from pathlib import Path

from loguru import logger

# 日志目录：HELLO/logs/
LOGS_DIR = Path(__file__).parent.parent / "logs"


def setup_logger(verbose: bool = False) -> None:
    """
    初始化 loguru 日志

    Args:
        verbose: 是否启用详细模式（控制台输出 INFO 级别）
    """
    logger.remove()

    # 控制台输出
    console_level = "INFO" if verbose else "WARNING"
    logger.add(
        sys.stderr,
        level=console_level,
        format="<level>{level: <8}</level> | <level>{message}</level>",
    )

    # 确保日志目录存在
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 文件输出：DEBUG 及以上，按日期分割
    log_file = LOGS_DIR / "hello_{time:YYYY-MM-DD}.log"
    logger.add(
        log_file,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",  # 每天午夜轮转
        retention="7 days",  # 保留 7 天
        encoding="utf-8",
    )
