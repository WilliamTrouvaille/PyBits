"""
PTM PDF 转 Markdown 工作流。
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from loguru import logger

from .api_client import MinerUAPIClient
from .config import load_token, mask_token
from .constants import (
    DEFAULT_DOWNLOAD_BACKOFF_SECONDS,
    DEFAULT_DOWNLOAD_RETRIES,
    MAX_DOWNLOAD_BACKOFF_SECONDS,
)
from .file_handler import download_zip, extract_markdown
from .models import PTMDownloadError, PTMError
from .output import build_output_name, prepare_output_dir
from .pdf_validator import validate_pdf


def convert_pdf_via_api(args: argparse.Namespace) -> Path:
    """
    通过 MinerU API 执行完整 PDF 转 Markdown 流程。

    Args:
        args: argparse 解析出的命名空间。

    Returns:
        最终 Markdown 文件路径。
    """

    _validate_runtime_options(args)
    pdf_path = validate_pdf(args.input_pdf)
    output_dir = prepare_output_dir(pdf_path, args.out_dir)
    output_name = build_output_name(pdf_path)
    zip_path = output_dir / f"{output_name}.zip"

    token = load_token()
    logger.info(f"使用 MinerU API token: {mask_token(token)}")

    client = MinerUAPIClient(token=token, proxy=args.proxy)
    batch_id, upload_url = client.create_batch_task(
        pdf_path,
        model_version=args.model_version,
        lang=args.lang,
        is_ocr=args.ocr,
        enable_table=args.enable_table,
        enable_formula=args.enable_formula,
        page_ranges=args.page_ranges,
    )
    client.upload_file(upload_url, pdf_path)
    result_zip_url = client.poll_result(
        batch_id,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
    )
    _download_result_zip_with_recovery(
        client,
        batch_id,
        result_zip_url,
        zip_path,
        proxy=args.proxy,
        retries=getattr(args, "download_retries", DEFAULT_DOWNLOAD_RETRIES),
        initial_backoff=getattr(
            args,
            "download_backoff",
            DEFAULT_DOWNLOAD_BACKOFF_SECONDS,
        ),
    )
    return extract_markdown(
        zip_path,
        output_dir,
        output_name,
        keep_images=args.images,
        keep_zip=args.keep_zip,
    )


def _download_result_zip_with_recovery(
    client: MinerUAPIClient,
    batch_id: str,
    result_zip_url: str,
    zip_path: Path,
    *,
    proxy: str | None,
    retries: int,
    initial_backoff: float,
) -> None:
    _validate_download_options(retries, initial_backoff)
    attempts = retries + 1
    current_url = result_zip_url
    last_error: PTMDownloadError | None = None

    for attempt in range(1, attempts + 1):
        try:
            logger.info(f"下载尝试 {attempt}/{attempts}")
            download_zip(current_url, zip_path, proxy=proxy)
            return
        except PTMDownloadError as exc:
            last_error = exc
            if not exc.retryable or attempt >= attempts:
                break

            logger.warning(f"下载失败，将重试: {exc.message}")
            if exc.refresh_url:
                current_url = _refresh_zip_url_for_retry(client, batch_id, current_url)

            delay = _download_retry_delay(attempt, initial_backoff)
            if delay > 0:
                logger.info(f"{delay:g} 秒后重试下载")
                time.sleep(delay)

    if last_error is None:
        raise PTMError(
            "Download failed for an unknown reason",
            "Check network connection and try again.",
        )
    raise PTMError(
        f"{last_error.message} after {attempts} attempt(s)",
        "Check network connection, try --proxy, or rerun PTM later.",
    ) from last_error


def _validate_runtime_options(args: argparse.Namespace) -> None:
    timeout = getattr(args, "timeout", 0)
    poll_interval = getattr(args, "poll_interval", 0)
    if timeout <= 0:
        raise PTMError("Invalid timeout: must be > 0", "Use --timeout with a positive integer.")
    if poll_interval <= 0:
        raise PTMError(
            "Invalid poll interval: must be > 0",
            "Use --poll-interval with a positive integer.",
        )
    _validate_download_options(
        getattr(args, "download_retries", DEFAULT_DOWNLOAD_RETRIES),
        getattr(args, "download_backoff", DEFAULT_DOWNLOAD_BACKOFF_SECONDS),
    )


def _validate_download_options(retries: int, initial_backoff: float) -> None:
    if retries < 0:
        raise PTMError(
            "Invalid download retries: must be >= 0",
            "Use --download-retries with a non-negative integer.",
        )
    if initial_backoff < 0:
        raise PTMError(
            "Invalid download backoff: must be >= 0",
            "Use --download-backoff with a non-negative number.",
        )


def _refresh_zip_url_for_retry(
    client: MinerUAPIClient,
    batch_id: str,
    fallback_url: str,
) -> str:
    try:
        refreshed_url = client.refresh_result_zip_url(batch_id)
    except PTMError as exc:
        logger.warning(f"重新拉取结果 URL 失败，将复用上一次 URL: {exc.message}")
        return fallback_url

    if refreshed_url != fallback_url:
        logger.info("已通过 batch_id 获取新的结果 zip URL")
    return refreshed_url


def _download_retry_delay(attempt: int, initial_backoff: float) -> float:
    if initial_backoff <= 0:
        return 0.0
    return min(initial_backoff * (2 ** (attempt - 1)), MAX_DOWNLOAD_BACKOFF_SECONDS)
