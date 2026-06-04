"""
PTM 输出路径辅助函数。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .models import PTMError


def prepare_output_dir(input_pdf: Path, out_dir: str | None) -> Path:
    """
    解析并创建 PTM 输出目录。

    Args:
        input_pdf: 输入 PDF 路径。
        out_dir: 用户指定的输出目录；为 None 时使用输入 PDF 所在目录。

    Returns:
        解析后的绝对输出目录。

    Raises:
        PTMError: 输出目录无法创建。
    """

    output_dir = Path(out_dir).expanduser() if out_dir else input_pdf.parent
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PTMError(
            f"无法创建输出目录: {output_dir}",
            f"检查路径权限后重试。细节: {exc}",
        ) from exc
    return output_dir.resolve()


def build_output_name(input_pdf: Path) -> str:
    """
    生成带时间戳的 PTM 输出文件基础名。

    Args:
        input_pdf: 输入 PDF 路径。

    Returns:
        不含扩展名的输出文件基础名。
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{input_pdf.stem}_PTM_{timestamp}"
