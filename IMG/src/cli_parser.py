"""IMG 命令行参数解析器。"""

from __future__ import annotations

import argparse

from .constants import (
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_QUALITY,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_SIZE,
)


def build_parser() -> argparse.ArgumentParser:
    """
    构建 IMG 命令行参数解析器。

    Returns:
        已配置的 argparse 参数解析器。
    """

    parser = argparse.ArgumentParser(
        prog="IMG",
        description="通过 OpenAI Images API 兼容后端生成图片。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="生成图片。")
    prompt_group = generate_parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="直接提供图片生成提示词。")
    prompt_group.add_argument("--prompt-file", help="从文本文件读取图片生成提示词。")
    generate_parser.add_argument("--out", required=True, help="输出图片路径。")
    generate_parser.add_argument("--provider", help="指定 IMG/.env 中的 provider。")
    generate_parser.add_argument("--model", help="覆盖当前 provider 的默认模型。")
    generate_parser.add_argument(
        "--size",
        default=DEFAULT_SIZE,
        help=f"图片尺寸，默认: {DEFAULT_SIZE}。",
    )
    generate_parser.add_argument(
        "--quality",
        choices=["low", "medium", "high", "auto"],
        default=DEFAULT_QUALITY,
        help=f"图片质量，默认: {DEFAULT_QUALITY}。",
    )
    generate_parser.add_argument(
        "--output-format",
        choices=["png", "jpeg", "jpg", "webp"],
        default=DEFAULT_OUTPUT_FORMAT,
        help=f"输出格式，默认: {DEFAULT_OUTPUT_FORMAT}。",
    )
    generate_parser.add_argument("--n", type=int, default=1, help="生成数量，默认: 1。")
    generate_parser.add_argument("--force", action="store_true", help="允许覆盖已有输出文件。")
    generate_parser.add_argument("--dry-run", action="store_true", help="只打印请求摘要。")
    generate_parser.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        help=f"请求超时时间，单位秒，默认: {DEFAULT_REQUEST_TIMEOUT_SECONDS:g}。",
    )
    generate_parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志。")

    return parser
