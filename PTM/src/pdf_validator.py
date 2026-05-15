"""PDF validation helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path

from loguru import logger

from .constants import MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB, MAX_PAGE_COUNT
from .models import PTMError

PDF_MAGIC = b"%PDF-"


def estimate_pdf_pages(pdf_path: Path) -> int:
    """Estimate PDF page count without adding a PDF parser dependency."""

    content = pdf_path.read_bytes()
    counts = [int(match) for match in re.findall(rb"/Count\s+(\d+)", content)]
    if counts:
        return max(counts)

    page_matches = re.findall(rb"/Type\s*/Page\b", content)
    return max(len(page_matches), 1)


def validate_pdf(pdf_path: str | Path) -> Path:
    """Validate that the input is a readable PDF within MinerU API limits."""

    path = Path(pdf_path).expanduser()

    if not path.exists():
        raise PTMError(
            f"File not found: {path}",
            "Check the file path and try again.",
        )
    if not path.is_file():
        raise PTMError(
            f"Not a file: {path}",
            "Provide a PDF file path, not a directory.",
        )
    if not os.access(path, os.R_OK):
        raise PTMError(
            f"File is not readable: {path}",
            "Check file permissions and try again.",
        )
    if path.suffix.lower() != ".pdf":
        raise PTMError(
            f"Not a valid PDF file: {path}",
            "Provide a file with .pdf extension and valid PDF format.",
        )

    try:
        with path.open("rb") as file:
            magic = file.read(len(PDF_MAGIC))
    except OSError as exc:
        raise PTMError(
            f"Cannot read file: {path}",
            f"Check file permissions and try again. Details: {exc}",
        ) from exc

    if magic != PDF_MAGIC:
        raise PTMError(
            f"Not a valid PDF file: {path}",
            "Provide a file with .pdf extension and valid PDF format.",
        )

    size_bytes = path.stat().st_size
    if size_bytes > MAX_FILE_SIZE_BYTES:
        size_mb = size_bytes / 1024 / 1024
        raise PTMError(
            f"File too large: {size_mb:.1f}MB (max {MAX_FILE_SIZE_MB}MB)",
            "Split the PDF or compress it.",
        )

    try:
        page_count = estimate_pdf_pages(path)
    except (OSError, ValueError) as exc:
        logger.warning(f"无法估算 PDF 页数，将继续交由 API 校验: {exc}")
    else:
        if page_count > MAX_PAGE_COUNT:
            raise PTMError(
                f"Too many pages: ~{page_count} pages (max {MAX_PAGE_COUNT})",
                "Split the PDF or use --page-ranges.",
            )

    return path.resolve()
