"""IMG 输出路径和图片写入辅助函数。"""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from urllib.parse import urlsplit

import requests

from .models import GeneratedImage, IMGError

MAX_IMAGE_DOWNLOAD_BYTES = 100 * 1024 * 1024


def normalize_output_format(output_format: str | None) -> str:
    """
    规范化输出格式名称。
    """

    value = (output_format or "png").strip().lower()
    if value == "jpg":
        return "jpeg"
    if value not in {"png", "jpeg", "webp"}:
        raise IMGError(
            "--output-format 只支持 png、jpeg、jpg 或 webp",
            "使用 OpenAI Images API 兼容的输出格式。",
        )
    return value


def build_output_paths(out: str, output_format: str, count: int) -> list[Path]:
    """
    根据输出路径、格式和数量生成最终文件路径。
    """

    if count < 1:
        raise IMGError("--n 必须大于等于 1", "使用 1 到 10 之间的整数。")

    ext = f".{output_format}"
    out_path = Path(out).expanduser()
    if out_path.suffix == "":
        out_path = out_path.with_suffix(ext)

    if count == 1:
        return [out_path]

    return [
        out_path.with_name(f"{out_path.stem}-{index}{out_path.suffix}")
        for index in range(1, count + 1)
    ]


def ensure_outputs_available(paths: list[Path], *, force: bool) -> None:
    """
    在发送请求前确认输出路径不会被意外覆盖。
    """

    if force:
        return

    existing = [path for path in paths if path.exists()]
    if existing:
        first = existing[0]
        raise IMGError(
            f"输出文件已存在: {first}",
            "更换 --out 路径，或确认可以覆盖后添加 --force。",
        )


def write_base64_images(
    images: list[str],
    output_paths: list[Path],
    *,
    force: bool,
) -> list[Path]:
    """
    将 base64 图片内容写入目标路径。
    """

    generated = [GeneratedImage(source="b64_json", value=image) for image in images]
    return write_generated_images(generated, output_paths, force=force, download_timeout=120.0)


def write_generated_images(
    images: list[GeneratedImage],
    output_paths: list[Path],
    *,
    force: bool,
    download_timeout: float,
) -> list[Path]:
    """
    将生成图片写入目标路径，支持 b64_json 和 url 两种响应。
    """

    if len(images) != len(output_paths):
        raise IMGError(
            f"API 返回图片数量不匹配: 期望 {len(output_paths)}，实际 {len(images)}",
            "检查后端响应，或减少 --n 后重试。",
        )

    ensure_outputs_available(output_paths, force=force)
    written: list[Path] = []
    for image, output_path in zip(images, output_paths, strict=True):
        image_bytes = image_to_bytes(image, download_timeout=download_timeout)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_name(f".{output_path.name}.part")
        if temp_path.exists() and not force:
            raise IMGError(
                f"临时输出文件已存在: {temp_path}",
                "检查上一次运行是否中断；确认可覆盖后添加 --force。",
            )
        temp_path.write_bytes(image_bytes)
        os.replace(temp_path, output_path)
        written.append(output_path)
    return written


def image_to_bytes(image: GeneratedImage, *, download_timeout: float) -> bytes:
    """
    将生成图片内容转换为字节。
    """

    if image.source == "b64_json":
        try:
            return base64.b64decode(image.value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise IMGError(
                "API 返回的 b64_json 无法解码",
                "检查后端是否返回了 OpenAI Images API 兼容响应。",
            ) from exc

    if image.source == "url":
        return download_image_url(image.value, timeout=download_timeout)

    raise IMGError(
        f"未知图片响应类型: {image.source}",
        "检查后端是否返回 b64_json 或 url。",
    )


def download_image_url(url: str, *, timeout: float) -> bytes:
    """
    下载后端返回的图片 URL。
    """

    try:
        response = requests.get(url, timeout=timeout, stream=True)
    except requests.RequestException as exc:
        raise IMGError(
            f"下载图片 URL 失败: {safe_url_host(url)}",
            f"检查网络连接后重试。细节: {exc.__class__.__name__}",
        ) from exc

    if response.status_code < 200 or response.status_code >= 300:
        raise IMGError(
            f"下载图片 URL 失败: HTTP {response.status_code}",
            f"后端图片地址主机: {safe_url_host(url)}。",
        )

    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_IMAGE_DOWNLOAD_BYTES:
                raise IMGError(
                    "下载图片过大",
                    "当前单张图片下载上限为 100MB。",
                )
            chunks.append(chunk)
    finally:
        response.close()

    if not chunks:
        raise IMGError(
            "下载图片为空",
            "检查后端返回的图片 URL 是否有效。",
        )
    return b"".join(chunks)


def safe_url_host(url: str) -> str:
    """
    返回 URL 的 host，用于错误提示时避免输出完整签名 URL。
    """

    parts = urlsplit(url)
    return parts.netloc or "[unknown-host]"
