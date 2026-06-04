"""PTP 的 PDF 页面渲染辅助函数。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from _shared.utils.trash import soft_delete

SUPPORTED_FORMATS = {"png"}


class PTPError(Exception):
    """
    带恢复提示的 PTP 用户可见错误。
    """

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


@dataclass(frozen=True)
class RenderOptions:
    """
    PDF 渲染流程所需的参数。
    """

    input_pdf: Path
    out_dir: Path | None
    dpi: int
    pages: list[int] | None
    image_format: str
    force: bool


@dataclass(frozen=True)
class RenderResult:
    """
    PDF 渲染成功后的输出信息。
    """

    output_files: list[Path]
    page_count: int


def parse_pages_spec(raw_pages: str) -> list[int]:
    """
    解析形如 `1,3-5` 的 1-based 页码范围字符串。

    Args:
        raw_pages: 用户传入的页码范围文本。

    Returns:
        去重后保持输入顺序的 1-based 页码列表。

    Raises:
        PTPError: 页码文本格式无效。
    """

    pages: list[int] = []
    seen: set[int] = set()

    for raw_part in raw_pages.split(","):
        part = raw_part.strip()
        if not part:
            raise PTPError(
                f"无效的 --pages 值: {raw_pages}",
                '使用逗号分隔的页码或范围，例如 "1,3-5"。',
            )
        if "-" in part:
            start_text, end_text = _split_range(part, raw_pages)
            start = _parse_positive_int(start_text, raw_pages)
            end = _parse_positive_int(end_text, raw_pages)
            if start > end:
                raise PTPError(
                    f"无效的 --pages 范围: {part}",
                    "范围起点必须小于或等于终点。",
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
    """
    将选中的 PDF 页面渲染为图片文件。

    Args:
        options: 渲染参数。

    Returns:
        渲染结果，包括输出文件列表和 PDF 总页数。

    Raises:
        PTPError: 输入、输出或渲染过程失败。
    """

    pdf_path = _validate_pdf(options.input_pdf)
    image_format = _validate_format(options.image_format)

    try:
        import pymupdf
    except ImportError as exc:
        raise PTPError(
            "未安装 PyMuPDF。",
            "使用 `uv tool install --force --reinstall --refresh .` 安装项目依赖。",
        ) from exc

    logger.info(f"开始渲染 PDF: {pdf_path}")
    try:
        document = pymupdf.open(str(pdf_path))
    except Exception as exc:
        raise PTPError(
            f"无法打开 PDF: {pdf_path}",
            f"检查文件是否为有效 PDF。细节: {exc}",
        ) from exc

    with document:
        page_count = document.page_count
        if page_count < 1:
            raise PTPError(
                f"PDF 没有页面: {pdf_path}",
                "请使用至少包含一页的 PDF。",
            )
        page_numbers = _resolve_page_numbers(options.pages, page_count)
        output_dir = _resolve_output_dir(pdf_path, options.out_dir, page_count)
        output_files = _build_output_files(
            pdf_path, output_dir, page_numbers, page_count, image_format
        )
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
                    f"无法将第 {page_number} 页渲染到 {output_file}",
                    f"检查输出路径权限和 PDF 页面内容。细节: {exc}",
                ) from exc

    logger.info(f"PDF 渲染完成: {len(output_files)} 个文件")
    return RenderResult(output_files=output_files, page_count=page_count)


def _split_range(part: str, raw_pages: str) -> tuple[str, str]:
    """
    将单个页码范围片段拆成起点和终点文本。
    """

    range_parts = part.split("-")
    if len(range_parts) != 2 or not range_parts[0].strip() or not range_parts[1].strip():
        raise PTPError(
            f"无效的 --pages 值: {raw_pages}",
            '使用逗号分隔的页码或范围，例如 "1,3-5"。',
        )
    return range_parts[0].strip(), range_parts[1].strip()


def _parse_positive_int(raw_value: str, raw_pages: str) -> int:
    """
    将页码文本解析为正整数。
    """

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise PTPError(
            f"无效的 --pages 值: {raw_pages}",
            "页码必须是正整数。",
        ) from exc
    if value < 1:
        raise PTPError(
            f"无效的 --pages 值: {raw_pages}",
            "页码必须大于 0。",
        )
    return value


def _validate_pdf(raw_path: Path) -> Path:
    """
    校验输入路径是可渲染的 PDF 文件。
    """

    pdf_path = raw_path.expanduser().resolve()
    if not pdf_path.exists():
        raise PTPError(
            f"文件不存在: {pdf_path}",
            "检查输入 PDF 路径后重试。",
        )
    if not pdf_path.is_file():
        raise PTPError(
            f"输入路径不是文件: {pdf_path}",
            "请传入 PDF 文件路径。",
        )
    if pdf_path.suffix.lower() != ".pdf":
        raise PTPError(
            f"输入文件不是 PDF: {pdf_path}",
            "请传入 .pdf 扩展名的文件。",
        )
    return pdf_path


def _validate_format(raw_format: str) -> str:
    """
    校验输出图片格式。
    """

    image_format = raw_format.lower()
    if image_format not in SUPPORTED_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_FORMATS))
        raise PTPError(
            f"不支持的输出格式: {raw_format}",
            f"可用格式: {supported}。",
        )
    return image_format


def _resolve_page_numbers(selected_pages: list[int] | None, page_count: int) -> list[int]:
    """
    根据用户选择和 PDF 总页数生成实际渲染页码。
    """

    page_numbers = selected_pages if selected_pages is not None else list(range(1, page_count + 1))
    invalid_pages = [page_number for page_number in page_numbers if page_number > page_count]
    if invalid_pages:
        raise PTPError(
            f"页码超出范围: {invalid_pages[0]}",
            f"该 PDF 共有 {page_count} 页，请使用 1 到 {page_count} 之间的页码。",
        )
    return page_numbers


def _resolve_output_dir(pdf_path: Path, raw_out_dir: Path | None, page_count: int) -> Path:
    """
    解析渲染输出目录。
    """

    if raw_out_dir is not None:
        output_dir = raw_out_dir.expanduser()
    elif page_count == 1:
        output_dir = pdf_path.parent
    else:
        output_dir = pdf_path.parent / f"{pdf_path.stem}_PTP"

    if output_dir.exists() and not output_dir.is_dir():
        raise PTPError(
            f"输出路径已存在且不是目录: {output_dir}",
            "请选择其他 --out-dir。",
        )
    return output_dir.resolve()


def _ensure_output_dir(output_dir: Path) -> None:
    """
    创建输出目录。
    """

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PTPError(
            f"无法创建输出目录: {output_dir}",
            f"检查路径权限后重试。细节: {exc}",
        ) from exc


def _build_output_files(
    pdf_path: Path,
    output_dir: Path,
    page_numbers: list[int],
    page_count: int,
    image_format: str,
) -> list[Path]:
    """
    根据页码和 PDF 页数生成输出文件路径列表。
    """

    if page_count == 1 and page_numbers == [1]:
        return [output_dir / f"{pdf_path.stem}.{image_format}"]

    return [
        output_dir / f"{pdf_path.stem}_{page_number:03d}.{image_format}"
        for page_number in page_numbers
    ]


def _prepare_output_targets(output_files: list[Path], force: bool) -> None:
    """
    校验输出目标；启用 force 时软删除已有文件。
    """

    for output_file in output_files:
        if not output_file.exists():
            continue
        if not force:
            raise PTPError(
                f"输出文件已存在: {output_file}",
                "使用 --force 软删除旧文件后再写入新文件。",
            )
        deleted_path = soft_delete(output_file, "ptp-overwrite")
        logger.info(f"已软删除旧输出: {output_file} -> {deleted_path}")
