"""用户反馈 - 旋转图标"""

import sys
from collections.abc import Generator
from contextlib import contextmanager

from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner as RichSpinner


class Spinner:
    """旋转图标管理器"""

    def __init__(self, message: str, spinner_type: str = "dots") -> None:
        """
        初始化 Spinner

        Args:
            message: 显示的消息
            spinner_type: 旋转图标类型（dots, line, arc 等）
        """
        self.message = message
        self.spinner_type = spinner_type
        self.console = Console(stderr=True)
        self._live: Live | None = None

    def start(self) -> None:
        """启动 spinner"""
        if not sys.stderr.isatty():
            # 非交互式终端，仅记录日志
            logger.info(self.message)
            return

        spinner = RichSpinner(self.spinner_type, text=self.message)
        self._live = Live(spinner, console=self.console, transient=True)
        self._live.start()

    def stop(self, final_message: str | None = None) -> None:
        """
        停止 spinner

        Args:
            final_message: 停止后显示的最终消息
        """
        if self._live:
            self._live.stop()
            self._live = None

        if final_message:
            self.console.print(final_message, style="green")

    def succeed(self, final_message: str) -> None:
        """
        标记 spinner 成功结束

        Args:
            final_message: 成功后显示的最终消息
        """
        self.stop(final_message)

    def update(self, message: str) -> None:
        """
        更新 spinner 消息

        Args:
            message: 新消息
        """
        self.message = message
        if self._live:
            spinner = RichSpinner(self.spinner_type, text=message)
            self._live.update(spinner)
        else:
            # 非交互式终端，记录日志
            logger.info(message)


@contextmanager
def with_spinner(
    message: str, final_message: str | None = None
) -> Generator[Spinner]:
    """
    Spinner 上下文管理器

    Args:
        message: 显示的消息
        final_message: 完成后的消息

    Yields:
        Spinner 实例

    Example:
        with with_spinner("Probing Claude Code...") as spinner:
            result = probe_claude(args, workdir)
            spinner.update("Processing response...")
    """
    spinner = Spinner(message)
    spinner.start()
    try:
        yield spinner
    finally:
        spinner.stop(final_message)
