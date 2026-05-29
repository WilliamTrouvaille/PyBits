"""Command-line entry point for PTP."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from _shared.utils.logging import setup_tool_logger

from .src.converter import PTPError, RenderOptions, parse_pages_spec, render_pdf

LOGS_DIR = Path(__file__).parent / "logs"
DEFAULT_DPI = 200


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="PTP",
        description="Render PDF pages to PNG images with PyMuPDF.",
    )
    parser.add_argument("input_pdf", help="Input PDF file path.")
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"Rendering DPI (default: {DEFAULT_DPI}).",
    )
    page_group = parser.add_mutually_exclusive_group()
    page_group.add_argument(
        "--page",
        type=int,
        help="Render a single 1-based page number.",
    )
    page_group.add_argument(
        "--pages",
        help='Render page ranges, for example: "1,3-5".',
    )
    parser.add_argument(
        "--out-dir",
        help="Output directory. Defaults to the input PDF directory for single-page PDFs "
        "or <input>_PTP for multi-page PDFs.",
    )
    parser.add_argument(
        "--format",
        default="png",
        choices=["png"],
        help="Output image format (default: png).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Soft-delete existing output files before writing new ones.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose logs.")
    return parser


def selected_pages_from_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> list[int] | None:
    """Parse optional page selection arguments."""

    if args.dpi <= 0:
        parser.error("--dpi must be greater than 0")
    if args.page is not None:
        if args.page <= 0:
            parser.error("--page must be greater than 0")
        return [args.page]
    if args.pages:
        try:
            return parse_pages_spec(args.pages)
        except PTPError as exc:
            parser.error(exc.message)
    return None


def main() -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args()
    setup_tool_logger("ptp", logs_dir=LOGS_DIR, verbose=args.verbose, retention_days=30)

    try:
        result = render_pdf(
            RenderOptions(
                input_pdf=Path(args.input_pdf),
                out_dir=Path(args.out_dir) if args.out_dir else None,
                dpi=args.dpi,
                pages=selected_pages_from_args(parser, args),
                image_format=args.format,
                force=args.force,
            )
        )
    except PTPError as exc:
        logger.error(exc.message)
        print(f"ERROR: {exc.message}", file=sys.stderr)
        print(f"HINT: {exc.hint}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ERROR: Interrupted by user", file=sys.stderr)
        print("HINT: Run the command again when ready.", file=sys.stderr)
        return 1
    except Exception:
        logger.exception("Unexpected error")
        print("ERROR: Unexpected error", file=sys.stderr)
        print("HINT: Check the traceback above or rerun with --verbose.", file=sys.stderr)
        return 1

    for output_file in result.output_files:
        print(output_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
