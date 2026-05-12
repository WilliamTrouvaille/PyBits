"""CLI 参数解析和入口。"""

import argparse
import sys
from pathlib import Path

from loguru import logger

from PTM.core import convert_pdf, prepare_mineru_runtime
from PTM.utils import format_error, generate_timestamp, validate_output_dir, validate_pdf

logger.remove()
logger.add(sys.stderr, format="[{level}] {message}", level="INFO")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="PTM - PDF to Markdown converter using MinerU",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("input_pdf", type=str, help="输入 PDF 文件路径")

    parser.add_argument(
        "--out-dir", type=str, default=None, help="输出目录（默认：输入文件同目录）"
    )

    parser.add_argument("--images", action="store_true", help="是否输出图片到 imgs/ 文件夹")

    parser.add_argument(
        "--engine",
        type=str,
        default="mineru",
        choices=["mineru"],
        help="转换引擎（当前仅支持 mineru）",
    )

    parser.add_argument("--timeout", type=int, default=300, help="超时时间（秒，默认 300）")

    parser.add_argument(
        "--model-source",
        type=str,
        default="modelscope",
        choices=["modelscope", "huggingface"],
        help="模型源（默认 modelscope）",
    )

    parser.add_argument("--proxy", type=str, default=None, help="代理地址")

    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> tuple[Path, Path, str]:
    """验证参数并返回处理后的路径。

    Returns:
        (input_pdf_path, output_dir_path, output_filename)
    """
    input_pdf = Path(args.input_pdf).resolve()

    is_valid, error_msg, hint_msg = validate_pdf(input_pdf)
    if not is_valid:
        format_error(error_msg, hint_msg)

    if args.timeout <= 0:
        format_error(
            "ERROR: 超时时间必须为正整数", f"HINT: 当前值为 {args.timeout}，请提供大于 0 的整数"
        )

    output_dir = Path(args.out_dir).resolve() if args.out_dir else input_pdf.parent

    timestamp = generate_timestamp()
    output_filename = f"{input_pdf.stem}_PTM_{timestamp}.md"

    is_valid, error_msg, hint_msg = validate_output_dir(output_dir, output_filename, args.images)
    if not is_valid:
        format_error(error_msg, hint_msg)

    return input_pdf, output_dir, output_filename


def main() -> None:
    """主入口函数。"""
    args = parse_args()
    input_pdf, output_dir, output_filename = validate_args(args)

    logger.info(f"输入文件: {input_pdf}")
    logger.info(f"输出目录: {output_dir}")
    logger.info(f"输出文件: {output_filename}")
    logger.info(f"图片输出: {'启用' if args.images else '禁用'}")
    logger.info(f"超时时间: {args.timeout} 秒")

    success, mineru_config, error_msg, hint_msg = prepare_mineru_runtime(
        args.model_source, args.proxy
    )
    if not success or mineru_config is None:
        format_error(error_msg, hint_msg)

    success, error_msg, hint_msg = convert_pdf(
        input_pdf=input_pdf,
        output_dir=output_dir,
        output_filename=output_filename,
        enable_images=args.images,
        engine=args.engine,
        timeout=args.timeout,
        model_source=args.model_source,
        proxy=args.proxy,
        mineru_config=mineru_config,
    )

    if not success:
        format_error(error_msg, hint_msg)

    logger.info("转换成功完成")
    sys.exit(0)


if __name__ == "__main__":
    main()
