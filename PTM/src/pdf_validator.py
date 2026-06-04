"""PTM 的 PDF 输入校验辅助函数。"""

from __future__ import annotations

import os
import re
from pathlib import Path

from loguru import logger

from .constants import MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB, MAX_PAGE_COUNT
from .models import PTMError

PDF_MAGIC = b"%PDF-"


def estimate_pdf_pages(pdf_path: Path) -> int:
    """
    在不额外引入 PDF 解析器的前提下估算页数。

    Args:
        pdf_path: PDF 文件路径。

    Returns:
        估算页数；无法从 `/Count` 推断时按 `/Page` 计数兜底。
    """

    content = pdf_path.read_bytes()
    counts = [int(match) for match in re.findall(rb"/Count\s+(\d+)", content)]
    if counts:
        return max(counts)

    page_matches = re.findall(rb"/Type\s*/Page\b", content)
    return max(len(page_matches), 1)


def validate_pdf(pdf_path: str | Path) -> Path:
    """
    校验输入文件是可读且符合 MinerU 限制的 PDF。

    Args:
        pdf_path: 用户传入的 PDF 路径。

    Returns:
        解析后的绝对 PDF 路径。

    Raises:
        PTMError: 文件不存在、不可读、不是 PDF 或超过 MinerU 限制。
    """

    path = Path(pdf_path).expanduser()

    if not path.exists():
        raise PTMError(
            f"文件不存在: {path}",
            "检查文件路径后重试。",
        )
    if not path.is_file():
        raise PTMError(
            f"不是文件: {path}",
            "请提供 PDF 文件路径，而不是目录。",
        )
    if not os.access(path, os.R_OK):
        raise PTMError(
            f"文件不可读: {path}",
            "检查文件权限后重试。",
        )
    if path.suffix.lower() != ".pdf":
        raise PTMError(
            f"不是有效 PDF 文件: {path}",
            "请提供 .pdf 扩展名且格式有效的 PDF 文件。",
        )

    try:
        with path.open("rb") as file:
            magic = file.read(len(PDF_MAGIC))
    except OSError as exc:
        raise PTMError(
            f"无法读取文件: {path}",
            f"检查文件权限后重试。细节: {exc}",
        ) from exc

    if magic != PDF_MAGIC:
        raise PTMError(
            f"不是有效 PDF 文件: {path}",
            "请提供 .pdf 扩展名且格式有效的 PDF 文件。",
        )

    size_bytes = path.stat().st_size
    if size_bytes > MAX_FILE_SIZE_BYTES:
        size_mb = size_bytes / 1024 / 1024
        raise PTMError(
            f"文件过大: {size_mb:.1f}MB (上限 {MAX_FILE_SIZE_MB}MB)",
            "拆分或压缩 PDF 后重试。",
        )

    try:
        page_count = estimate_pdf_pages(path)
    except (OSError, ValueError) as exc:
        logger.warning(f"无法估算 PDF 页数，将继续交由 API 校验: {exc}")
    else:
        if page_count > MAX_PAGE_COUNT:
            raise PTMError(
                f"页数过多: 约 {page_count} 页 (上限 {MAX_PAGE_COUNT})",
                "拆分 PDF，或使用 --page-ranges。",
            )

    return path.resolve()
