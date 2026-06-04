"""MinerU 结果 zip 的下载和解压辅助函数。"""

from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import requests
from loguru import logger
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from _shared.utils.trash import soft_delete

from .constants import MAX_UNZIPPED_SIZE_BYTES, REQUEST_TIMEOUT_SECONDS
from .models import PTMDownloadError, PTMError


def download_zip(url: str, dest_path: Path, proxy: str | None = None) -> None:
    """
    下载 MinerU 结果 zip，并尽量续传已有的 `.part` 文件。

    Args:
        url: MinerU 结果 zip URL。
        dest_path: 最终 zip 文件路径。
        proxy: 可选 HTTP(S) 代理 URL。

    Raises:
        PTMDownloadError: 网络或 HTTP 下载失败，且可能允许上层重试。
        PTMError: 本地文件写入或续传状态检查失败。
    """

    proxies = {"http": proxy, "https": proxy} if proxy else None
    part_path = _partial_download_path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"下载结果 zip: {dest_path.name}")

    try:
        existing_size = _partial_size(part_path)
        headers = {"Range": f"bytes={existing_size}-"} if existing_size else None

        if existing_size:
            logger.info(f"检测到未完成下载，将从 {existing_size} bytes 继续")

        with requests.get(
            url,
            stream=True,
            headers=headers,
            proxies=proxies,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            if response.status_code == 416:
                _reset_partial_download(part_path)
                raise PTMDownloadError(
                    "续传失败: HTTP 416",
                    "已重置未完成 zip；PTM 会从头重试。",
                    retryable=True,
                    refresh_url=True,
                )

            if response.status_code < 200 or response.status_code >= 300:
                raise _download_http_error(response.status_code)

            mode = "ab" if existing_size and response.status_code == 206 else "wb"
            completed = existing_size if mode == "ab" else 0
            if existing_size and response.status_code == 200:
                logger.warning("下载服务未接受 Range 续传，将重新下载结果 zip")
                _reset_partial_download(part_path)

            total = int(response.headers.get("content-length") or 0)
            if mode == "ab" and total:
                total += existing_size
            console = Console(stderr=True)
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
                transient=True,
                disable=not sys.stderr.isatty(),
            ) as progress:
                task_id = progress.add_task(
                    "下载结果",
                    total=total or None,
                    completed=completed,
                )
                with part_path.open(mode) as file:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        file.write(chunk)
                        progress.update(task_id, advance=len(chunk))

        part_path.replace(dest_path)
    except PTMError:
        raise
    except requests.RequestException as exc:
        raise PTMDownloadError(
            f"下载失败: {_safe_request_error(exc)}",
            "检查网络连接；如果仍有重试次数，PTM 会自动重试。",
            retryable=True,
            refresh_url=True,
        ) from exc
    except OSError as exc:
        raise PTMError(
            f"无法写入 zip 文件: {dest_path}",
            f"检查输出目录权限。细节: {exc}",
        ) from exc

    logger.info("结果 zip 下载完成")


def _partial_download_path(dest_path: Path) -> Path:
    """
    返回结果 zip 对应的未完成下载路径。
    """

    return dest_path.with_name(f"{dest_path.name}.part")


def _partial_size(part_path: Path) -> int:
    try:
        return part_path.stat().st_size
    except FileNotFoundError:
        return 0
    except OSError as exc:
        raise PTMError(
            f"无法检查未完成 zip 文件: {part_path}",
            f"检查输出目录权限。细节: {exc}",
        ) from exc


def _reset_partial_download(part_path: Path) -> None:
    """
    将损坏或不可续传的 `.part` 文件软删除。
    """

    if not part_path.exists():
        return
    moved_path = soft_delete(part_path, "ptm-partial-download")
    logger.debug(f"未完成 zip 已软删除: {part_path} -> {moved_path}")


def _download_http_error(status_code: int) -> PTMDownloadError:
    """
    将下载 HTTP 状态码转换为可恢复性明确的错误。
    """

    retryable = status_code in {403, 404, 408, 425, 429} or status_code >= 500
    refresh_url = status_code in {403, 404, 408, 425, 429} or status_code >= 500
    return PTMDownloadError(
        f"下载失败: HTTP {status_code}",
        "检查网络连接；如果仍有重试次数，PTM 会自动重试。",
        retryable=retryable,
        refresh_url=refresh_url,
    )


def extract_markdown(
    zip_path: Path,
    out_dir: Path,
    output_name: str,
    *,
    keep_images: bool,
    keep_zip: bool,
) -> Path:
    """
    从 MinerU 结果 zip 中提取 `full.md` 并生成最终 Markdown 文件。

    Args:
        zip_path: MinerU 结果 zip 路径。
        out_dir: 输出目录。
        output_name: 不含扩展名的输出基础名。
        keep_images: 是否复制 zip 内的 images/ 目录。
        keep_zip: 是否保留下载的 zip 文件。

    Returns:
        最终 Markdown 文件路径。

    Raises:
        PTMError: zip 损坏、内容不安全、缺少 full.md 或输出路径冲突。
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = out_dir / f"{output_name}.md"
    if markdown_path.exists():
        raise PTMError(
            f"输出文件已存在: {markdown_path}",
            "稍后重新运行，或选择其他输出目录。",
        )
    if keep_images:
        _validate_images_target(out_dir)

    try:
        with zipfile.ZipFile(zip_path) as archive:
            _validate_zip(archive)
            with tempfile.TemporaryDirectory(prefix=f"_temp_{output_name}_", dir=out_dir) as temp:
                temp_dir = Path(temp)
                archive.extractall(temp_dir)
                full_md = _find_full_markdown(temp_dir)
                shutil.copy2(full_md, markdown_path)

                if keep_images:
                    _copy_images(temp_dir, out_dir)
    except zipfile.BadZipFile as exc:
        raise PTMError(
            f"zip 文件无效: {zip_path}",
            "稍后重试，或联系 MinerU 支持。",
        ) from exc
    except PTMError:
        raise
    except OSError as exc:
        raise PTMError(
            f"提取 Markdown 失败: {exc}",
            "检查输出目录权限后重试。",
        ) from exc

    if not keep_zip:
        try:
            moved_zip = soft_delete(zip_path, "ptm-temp-zip")
            logger.debug(f"临时 zip 已软删除: {zip_path} -> {moved_zip}")
        except OSError as exc:
            logger.warning(f"无法删除临时 zip 文件，请手动处理: {zip_path} ({exc})")

    logger.info(f"Markdown 已生成: {markdown_path}")
    return markdown_path


def _validate_zip(archive: zipfile.ZipFile) -> None:
    """
    校验 zip 解压规模和成员路径，避免危险路径写入。
    """

    total_size = 0
    for info in archive.infolist():
        total_size += info.file_size
        if total_size > MAX_UNZIPPED_SIZE_BYTES:
            raise PTMError(
                "zip 解压后内容过大",
                "联系 MinerU 支持，或换用更小的 PDF。",
            )

        path = Path(info.filename)
        if path.is_absolute() or ".." in path.parts:
            raise PTMError(
                "检测到不安全的 zip 内容",
                "联系 MinerU 支持，不要手动解压该文件。",
            )


def _find_full_markdown(temp_dir: Path) -> Path:
    """
    在临时解压目录中查找 MinerU 输出的 `full.md`。
    """

    root_markdown = temp_dir / "full.md"
    if root_markdown.is_file():
        return root_markdown

    matches = sorted(temp_dir.rglob("full.md"))
    if matches:
        return matches[0]

    raise PTMError(
        "MinerU 结果 zip 中未找到 full.md",
        "稍后重试，或联系 MinerU 支持。",
    )


def _copy_images(temp_dir: Path, out_dir: Path) -> None:
    """
    将解压结果中的 images/ 目录复制到输出目录。
    """

    image_dir = temp_dir / "images"
    if not image_dir.is_dir():
        candidates = [path for path in temp_dir.rglob("images") if path.is_dir()]
        image_dir = candidates[0] if candidates else image_dir

    if not image_dir.is_dir():
        logger.warning("结果 zip 中未找到 images/ 目录")
        return

    target = out_dir / "images"
    _validate_images_target(out_dir)
    shutil.copytree(image_dir, target)


def _validate_images_target(out_dir: Path) -> None:
    """
    确认输出目录中尚不存在 images/ 目标。
    """

    target = out_dir / "images"
    if target.exists() or target.is_symlink():
        raise PTMError(
            f"images/ 目录已存在: {target}",
            "移除该目录，或禁用 --images。",
        )


def _safe_request_error(exc: requests.RequestException) -> str:
    """
    生成不会泄露签名 URL 查询串的请求错误摘要。
    """

    text = str(exc)
    request = getattr(exc, "request", None)
    url = getattr(request, "url", None)
    if url:
        text = text.replace(str(url), _redact_url(str(url)))
    return text


def _redact_url(url: str) -> str:
    """
    将 URL 缩减到 scheme 和 host，移除路径与查询串。
    """

    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return "[redacted-url]"
    return f"{parts.scheme}://{parts.netloc}/[redacted]"
