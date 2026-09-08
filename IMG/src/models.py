"""IMG 的领域模型和异常类型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class IMGError(Exception):
    """
    带恢复提示的 IMG 用户可见错误。
    """

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


@dataclass(frozen=True)
class ProviderConfig:
    """
    单个图片生成后端的配置。
    """

    name: str
    base_url: str
    api_key: str
    model: str
    dotenv_path: Path


@dataclass(frozen=True)
class GeneratePlan:
    """
    一次图片生成请求的最终计划。
    """

    provider: ProviderConfig
    payload: dict[str, Any]
    output_paths: list[Path]


@dataclass(frozen=True)
class GeneratedImage:
    """
    单张生成图片的返回内容。
    """

    source: str
    value: str
