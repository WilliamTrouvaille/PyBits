"""工具函数"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from .config import LOG_LEVEL, LOG_RETENTION_DAYS, LOGS_DIR


def setup_logger() -> None:
    """初始化 loguru 日志"""
    logger.remove()

    # 控制台输出：WARNING 及以上
    logger.add(
        sys.stderr,
        level="WARNING",
        format="<level>{level: <8}</level> | <level>{message}</level>",
    )

    # 确保日志目录存在
    ensure_dir(LOGS_DIR)

    # 文件输出：INFO 及以上，按日期分割
    log_file = LOGS_DIR / "skills_{time:YYYY-MM-DD}.log"
    logger.add(
        log_file,
        level=LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",
        retention=f"{LOG_RETENTION_DAYS} days",
        encoding="utf-8",
    )

    # 清理旧日志
    clean_old_logs(LOGS_DIR, LOG_RETENTION_DAYS)


def configure_git_proxy(proxy: str) -> dict[str, str]:
    """配置 git 代理环境变量"""
    return {
        "http_proxy": proxy,
        "https_proxy": proxy,
    }


def normalize_repo_name(url_or_path: str) -> str:
    """
    规范化仓库名称
    - GitHub: owner/repo
    - 本地: 目录名
    """
    if "/" in url_or_path and not url_or_path.startswith(("http://", "https://")):
        return url_or_path

    if url_or_path.startswith(("http://", "https://")):
        parts = url_or_path.rstrip("/").split("/")
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1].replace('.git', '')}"

    return Path(url_or_path).name


def ensure_dir(path: Path) -> None:
    """确保目录存在，不存在则创建"""
    path.mkdir(parents=True, exist_ok=True)


def clean_old_logs(logs_dir: Path, retention_days: int) -> None:
    """清理超过保留期限的日志文件"""
    if not logs_dir.exists():
        return

    cutoff_date = datetime.now() - timedelta(days=retention_days)

    for log_file in logs_dir.glob("skills_*.log"):
        try:
            # 从文件名提取日期
            date_str = log_file.stem.replace("skills_", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")

            if file_date < cutoff_date:
                log_file.unlink()
                logger.debug(f"删除旧日志文件: {log_file}")
        except (ValueError, OSError) as e:
            logger.warning(f"清理日志文件失败: {log_file}, 错误: {e}")
