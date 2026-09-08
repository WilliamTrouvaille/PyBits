"""OpenAI Images API 兼容客户端。"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlsplit

import requests
from loguru import logger

from .constants import GENERATION_ENDPOINT
from .models import GeneratedImage, IMGError, ProviderConfig


class ImageAPIClient:
    """
    封装 OpenAI Images API 兼容的图片生成请求。
    """

    def __init__(self, provider: ProviderConfig, timeout_seconds: float) -> None:
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {provider.api_key}",
                "Content-Type": "application/json",
            }
        )

    def generate(self, payload: dict[str, Any]) -> list[GeneratedImage]:
        """
        发送图片生成请求并返回图片内容引用。
        """

        url = build_endpoint_url(self.provider.base_url, GENERATION_ENDPOINT)
        logger.info(f"发送图片生成请求: provider={self.provider.name}")
        started = time.monotonic()
        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise IMGError(
                f"图片生成请求失败: {safe_request_error(exc)}",
                f"检查 provider `{self.provider.name}` 的 base URL、网络连接或代理设置。",
            ) from exc

        elapsed = time.monotonic() - started
        logger.info(f"图片生成请求完成: status={response.status_code}, elapsed={elapsed:.1f}s")
        return extract_generated_images(response)


def build_endpoint_url(base_url: str, endpoint: str) -> str:
    """
    拼接 base URL 与 API endpoint。
    """

    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def extract_b64_images(response: requests.Response) -> list[str]:
    """
    从 OpenAI Images API 兼容响应中提取 `b64_json`。
    """

    images = extract_generated_images(response)
    b64_images = [image.value for image in images if image.source == "b64_json"]
    if len(b64_images) == len(images):
        return b64_images
    raise IMGError(
        "图片生成响应只包含 URL",
        "当前调用路径只接受 b64_json；请使用通用图片写入流程。",
    )


def extract_generated_images(response: requests.Response) -> list[GeneratedImage]:
    """
    从 OpenAI Images API 兼容响应中提取图片内容。
    """

    if response.status_code in {401, 403}:
        raise IMGError(
            f"图片生成鉴权失败: HTTP {response.status_code}",
            "检查当前 provider 的 API key 是否有效。",
        )
    if response.status_code < 200 or response.status_code >= 300:
        raise IMGError(
            f"图片生成请求失败: HTTP {response.status_code}",
            f"后端返回: {response_text_summary(response)}",
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise IMGError(
            "图片生成响应不是 JSON",
            "检查后端是否兼容 OpenAI Images API。",
        ) from exc

    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise IMGError(
            "图片生成响应缺少 data 列表",
            "检查后端是否返回 OpenAI Images API 兼容响应。",
        )

    images: list[GeneratedImage] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        b64_json = item.get("b64_json")
        if isinstance(b64_json, str) and b64_json:
            images.append(GeneratedImage(source="b64_json", value=b64_json))
            continue
        url = item.get("url")
        if isinstance(url, str) and url:
            images.append(GeneratedImage(source="url", value=url))

    if images:
        return images

    raise IMGError(
        "图片生成响应缺少 b64_json 或 url",
        "检查后端是否返回 OpenAI Images API 兼容响应。",
    )


def response_text_summary(response: requests.Response) -> str:
    """
    返回长度受限的后端响应摘要。
    """

    text = response.text.strip()
    if not text:
        return "(空)"
    return text[:500]


def safe_request_error(exc: requests.RequestException) -> str:
    """
    生成不会泄露完整 URL 查询串的请求错误摘要。
    """

    text = str(exc)
    request = getattr(exc, "request", None)
    url = getattr(request, "url", None)
    if url:
        text = text.replace(str(url), redact_url(str(url)))
    return text


def redact_url(url: str) -> str:
    """
    将 URL 缩减到 scheme 和 host，移除路径与查询串。
    """

    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return "[redacted-url]"
    return f"{parts.scheme}://{parts.netloc}/[redacted]"
