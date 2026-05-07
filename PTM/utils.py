"""工具函数：时间戳生成、PDF验证、输出目录验证、错误格式化。"""

import os
import sys
from datetime import datetime
from pathlib import Path


def generate_timestamp() -> str:
    """生成时间戳（YYYYMMDD_HHMMSS）。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def validate_pdf(pdf_path: Path) -> tuple[bool, str, str]:
    """验证 PDF 文件。

    Returns:
        (is_valid, error_msg, hint_msg)
    """
    if not pdf_path.exists():
        return False, "ERROR: 无法读取输入文件", "HINT: 请检查文件路径是否正确"

    if not pdf_path.is_file():
        return False, "ERROR: 输入路径不是文件", "HINT: 请提供有效的 PDF 文件路径"

    if not os.access(pdf_path, os.R_OK):
        return False, "ERROR: 输入文件无读取权限", "HINT: 请检查文件权限"

    try:
        with open(pdf_path, "rb") as f:
            magic = f.read(4)
            if not magic.startswith(b"%PDF"):
                return False, "ERROR: 输入文件不是有效的 PDF", "HINT: 请提供 .pdf 格式的文件"
    except Exception as e:
        return False, f"ERROR: 读取文件失败: {e}", "HINT: 请检查文件是否损坏"

    return True, "", ""


def validate_output_dir(
    output_dir: Path, output_filename: str, check_images_dir: bool
) -> tuple[bool, str, str]:
    """验证输出目录。

    Args:
        output_dir: 输出目录路径
        output_filename: 输出文件名
        check_images_dir: 是否检查 imgs/ 文件夹

    Returns:
        (is_valid, error_msg, hint_msg)
    """
    if not output_dir.exists():
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"ERROR: 无法创建输出目录: {e}", "HINT: 请检查目录权限"

    if not os.access(output_dir, os.W_OK):
        return False, "ERROR: 输出目录无写入权限", "HINT: 请检查目录权限或更改输出目录"

    output_file = output_dir / output_filename
    if output_file.exists():
        return False, "ERROR: 输出文件已存在", "HINT: 请删除现有文件或更改输出目录"

    if check_images_dir:
        imgs_dir = output_dir / "imgs"
        if imgs_dir.exists():
            return False, "ERROR: imgs/ 文件夹已存在", "HINT: 请删除现有文件夹或禁用 --images"

    return True, "", ""


def format_error(error_msg: str, hint_msg: str) -> None:
    """格式化错误信息并输出到 stderr，然后退出。"""
    print(error_msg, file=sys.stderr)
    print(hint_msg, file=sys.stderr)
    sys.exit(1)
