"""PTM 的领域模型和异常类型。"""

from __future__ import annotations


class PTMError(Exception):
    """
    带恢复提示的 PTM 用户可见错误。
    """

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class PTMDownloadError(PTMError):
    """
    表示可能可以安全重试的下载失败。
    """

    def __init__(
        self,
        message: str,
        hint: str,
        *,
        retryable: bool,
        refresh_url: bool = True,
    ) -> None:
        super().__init__(message, hint)
        self.retryable = retryable
        self.refresh_url = refresh_url
