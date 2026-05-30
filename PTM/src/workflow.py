"""
PTM PDF 转 Markdown 工作流。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from .api_client import MinerUAPIClient
from .config import load_token, mask_token
from .file_handler import download_zip, extract_markdown
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
    download_zip(result_zip_url, zip_path, proxy=args.proxy)
    return extract_markdown(
        zip_path,
        output_dir,
        output_name,
        keep_images=args.images,
        keep_zip=args.keep_zip,
    )
