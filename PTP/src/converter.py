"""PDF rendering helpers for PTP."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from _shared.utils.trash import soft_delete

SUPPORTED_FORMATS = {"png"}


class PTPError(Exception):
    """Expected PTP error with a user-facing hint."""

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


@dataclass(frozen=True)
class RenderOptions:
    """Options for rendering a PDF file."""

    input_pdf: Path
    out_dir: Path | None
    dpi: int
    pages: list[int] | None
    image_format: str
    force: bool


@dataclass(frozen=True)
class RenderResult:
    """Result of a successful PDF render."""

    output_files: list[Path]
    page_count: int


def parse_pages_spec(raw_pages: str) -> list[int]:
    """Parse a 1-based page range string like `1,3-5`."""

    pages: list[int] = []
    seen: set[int] = set()

    for raw_part in raw_pages.split(","):
        part = raw_part.strip()
        if not part:
            raise PTPError(
                f"Invalid --pages value: {raw_pages}",
                'Use comma-separated page numbers or ranges, for example "1,3-5".',
            )
        if "-" in part:
            start_text, end_text = _split_range(part, raw_pages)
            start = _parse_positive_int(start_text, raw_pages)
            end = _parse_positive_int(end_text, raw_pages)
            if start > end:
                raise PTPError(
                    f"Invalid --pages range: {part}",
                    "Range start must be less than or equal to range end.",
                )
            for page_number in range(start, end + 1):
                if page_number not in seen:
                    pages.append(page_number)
                    seen.add(page_number)
            continue

        page_number = _parse_positive_int(part, raw_pages)
        if page_number not in seen:
            pages.append(page_number)
            seen.add(page_number)

    return pages


def render_pdf(options: RenderOptions) -> RenderResult:
    """Render selected PDF pages to image files."""

    pdf_path = _validate_pdf(options.input_pdf)
    image_format = _validate_format(options.image_format)

    try:
        import pymupdf
    except ImportError as exc:
        raise PTPError(
            "PyMuPDF is not installed.",
            "Install project dependencies with `uv tool install --force --reinstall --refresh .`.",
        ) from exc

    logger.info(f"开始渲染 PDF: {pdf_path}")
    try:
        document = pymupdf.open(str(pdf_path))
    except Exception as exc:
        raise PTPError(
            f"Cannot open PDF: {pdf_path}",
            f"Check whether the file is a valid PDF. Details: {exc}",
        ) from exc

    with document:
        page_count = document.page_count
        if page_count < 1:
            raise PTPError(
                f"PDF has no pages: {pdf_path}",
                "Use a PDF that contains at least one page.",
            )
        page_numbers = _resolve_page_numbers(options.pages, page_count)
        output_dir = _resolve_output_dir(pdf_path, options.out_dir, page_count)
        output_files = _build_output_files(pdf_path, output_dir, page_numbers, page_count, image_format)
        _prepare_output_targets(output_files, options.force)
        _ensure_output_dir(output_dir)

        for page_number, output_file in zip(page_numbers, output_files, strict=True):
            logger.info(f"渲染第 {page_number}/{page_count} 页: {output_file}")
            try:
                page = document.load_page(page_number - 1)
                pixmap = page.get_pixmap(dpi=options.dpi, alpha=False)
                pixmap.save(str(output_file))
            except Exception as exc:
                raise PTPError(
                    f"Cannot render page {page_number} to {output_file}",
                    f"Check output path permissions and PDF page content. Details: {exc}",
                ) from exc

    logger.info(f"PDF 渲染完成: {len(output_files)} file(s)")
    return RenderResult(output_files=output_files, page_count=page_count)


def _split_range(part: str, raw_pages: str) -> tuple[str, str]:
    range_parts = part.split("-")
    if len(range_parts) != 2 or not range_parts[0].strip() or not range_parts[1].strip():
        raise PTPError(
            f"Invalid --pages value: {raw_pages}",
            'Use comma-separated page numbers or ranges, for example "1,3-5".',
        )
    return range_parts[0].strip(), range_parts[1].strip()


def _parse_positive_int(raw_value: str, raw_pages: str) -> int:
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise PTPError(
            f"Invalid --pages value: {raw_pages}",
            "Page numbers must be positive integers.",
        ) from exc
    if value < 1:
        raise PTPError(
            f"Invalid --pages value: {raw_pages}",
            "Page numbers must be greater than 0.",
        )
    return value


def _validate_pdf(raw_path: Path) -> Path:
    pdf_path = raw_path.expanduser().resolve()
    if not pdf_path.exists():
        raise PTPError(
            f"File not found: {pdf_path}",
            "Check the input PDF path and try again.",
        )
    if not pdf_path.is_file():
        raise PTPError(
            f"Input path is not a file: {pdf_path}",
            "Pass a PDF file path.",
        )
    if pdf_path.suffix.lower() != ".pdf":
        raise PTPError(
            f"Input file is not a PDF: {pdf_path}",
            "Pass a file with the .pdf extension.",
        )
    return pdf_path


def _validate_format(raw_format: str) -> str:
    image_format = raw_format.lower()
    if image_format not in SUPPORTED_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_FORMATS))
        raise PTPError(
            f"Unsupported output format: {raw_format}",
            f"Use one of: {supported}.",
        )
    return image_format


def _resolve_page_numbers(selected_pages: list[int] | None, page_count: int) -> list[int]:
    page_numbers = selected_pages if selected_pages is not None else list(range(1, page_count + 1))
    invalid_pages = [page_number for page_number in page_numbers if page_number > page_count]
    if invalid_pages:
        raise PTPError(
            f"Page number out of range: {invalid_pages[0]}",
            f"This PDF has {page_count} page(s). Use a page number between 1 and {page_count}.",
        )
    return page_numbers


def _resolve_output_dir(pdf_path: Path, raw_out_dir: Path | None, page_count: int) -> Path:
    if raw_out_dir is not None:
        output_dir = raw_out_dir.expanduser()
    elif page_count == 1:
        output_dir = pdf_path.parent
    else:
        output_dir = pdf_path.parent / f"{pdf_path.stem}_PTP"

    if output_dir.exists() and not output_dir.is_dir():
        raise PTPError(
            f"Output path exists and is not a directory: {output_dir}",
            "Choose a different --out-dir.",
        )
    return output_dir.resolve()


def _ensure_output_dir(output_dir: Path) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PTPError(
            f"Cannot create output directory: {output_dir}",
            f"Check path permissions and try again. Details: {exc}",
        ) from exc


def _build_output_files(
    pdf_path: Path,
    output_dir: Path,
    page_numbers: list[int],
    page_count: int,
    image_format: str,
) -> list[Path]:
    if page_count == 1 and page_numbers == [1]:
        return [output_dir / f"{pdf_path.stem}.{image_format}"]

    return [output_dir / f"{pdf_path.stem}_{page_number:03d}.{image_format}" for page_number in page_numbers]


def _prepare_output_targets(output_files: list[Path], force: bool) -> None:
    for output_file in output_files:
        if not output_file.exists():
            continue
        if not force:
            raise PTPError(
                f"Output file already exists: {output_file}",
                "Use --force to soft-delete the old file before writing a new one.",
            )
        deleted_path = soft_delete(output_file, "ptp-overwrite")
        logger.info(f"已软删除旧输出: {output_file} -> {deleted_path}")
