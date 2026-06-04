"""Download and extraction helpers for MinerU zip results."""

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
    """Download a MinerU result zip file, resuming a previous partial download."""

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
                    "Download resume failed: HTTP 416",
                    "Partial zip was reset; PTM will retry from the beginning.",
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
            f"Download failed: {_safe_request_error(exc)}",
            "Check network connection; PTM will retry if attempts remain.",
            retryable=True,
            refresh_url=True,
        ) from exc
    except OSError as exc:
        raise PTMError(
            f"Cannot write zip file: {dest_path}",
            f"Check output directory permissions. Details: {exc}",
        ) from exc

    logger.info("结果 zip 下载完成")


def _partial_download_path(dest_path: Path) -> Path:
    return dest_path.with_name(f"{dest_path.name}.part")


def _partial_size(part_path: Path) -> int:
    try:
        return part_path.stat().st_size
    except FileNotFoundError:
        return 0
    except OSError as exc:
        raise PTMError(
            f"Cannot inspect partial zip file: {part_path}",
            f"Check output directory permissions. Details: {exc}",
        ) from exc


def _reset_partial_download(part_path: Path) -> None:
    if not part_path.exists():
        return
    moved_path = soft_delete(part_path, "ptm-partial-download")
    logger.debug(f"未完成 zip 已软删除: {part_path} -> {moved_path}")


def _download_http_error(status_code: int) -> PTMDownloadError:
    retryable = status_code in {403, 404, 408, 425, 429} or status_code >= 500
    refresh_url = status_code in {403, 404, 408, 425, 429} or status_code >= 500
    return PTMDownloadError(
        f"Download failed: HTTP {status_code}",
        "Check network connection; PTM will retry if attempts remain.",
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
    """Extract full.md from a MinerU result zip and return the final markdown path."""

    out_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = out_dir / f"{output_name}.md"
    if markdown_path.exists():
        raise PTMError(
            f"Output file already exists: {markdown_path}",
            "Run again later or choose another output directory.",
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
            f"Invalid zip file: {zip_path}",
            "Try again later or contact MinerU support.",
        ) from exc
    except PTMError:
        raise
    except OSError as exc:
        raise PTMError(
            f"Failed to extract markdown: {exc}",
            "Check output directory permissions and try again.",
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
    total_size = 0
    for info in archive.infolist():
        total_size += info.file_size
        if total_size > MAX_UNZIPPED_SIZE_BYTES:
            raise PTMError(
                "Zip content too large after extraction",
                "Contact MinerU support or try a smaller PDF.",
            )

        path = Path(info.filename)
        if path.is_absolute() or ".." in path.parts:
            raise PTMError(
                "Unsafe zip content detected",
                "Contact MinerU support and do not extract this file manually.",
            )


def _find_full_markdown(temp_dir: Path) -> Path:
    root_markdown = temp_dir / "full.md"
    if root_markdown.is_file():
        return root_markdown

    matches = sorted(temp_dir.rglob("full.md"))
    if matches:
        return matches[0]

    raise PTMError(
        "full.md not found in MinerU result zip",
        "Try again later or contact MinerU support.",
    )


def _copy_images(temp_dir: Path, out_dir: Path) -> None:
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
    target = out_dir / "images"
    if target.exists() or target.is_symlink():
        raise PTMError(
            f"images/ directory already exists: {target}",
            "Remove it or disable --images.",
        )


def _safe_request_error(exc: requests.RequestException) -> str:
    text = str(exc)
    request = getattr(exc, "request", None)
    url = getattr(request, "url", None)
    if url:
        text = text.replace(str(url), _redact_url(str(url)))
    return text


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return "[redacted-url]"
    return f"{parts.scheme}://{parts.netloc}/[redacted]"
