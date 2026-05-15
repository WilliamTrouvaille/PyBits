"""Command-line entry point for PTM."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from .src.api_client import MinerUAPIClient
from .src.config import load_token, mask_token
from .src.constants import (
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL_VERSION,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)
from .src.file_handler import download_zip, extract_markdown
from .src.models import PTMError
from .src.pdf_validator import validate_pdf


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="PTM",
        description="Convert local PDF files to Markdown via MinerU precise parsing API.",
    )
    parser.add_argument("input_pdf", help="Input PDF file path.")
    parser.add_argument(
        "--out-dir",
        help="Output directory. Defaults to the input PDF directory.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Total polling timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Polling interval in seconds (default: {DEFAULT_POLL_INTERVAL_SECONDS}).",
    )
    parser.add_argument(
        "--model-version",
        choices=["pipeline", "vlm", "MinerU-HTML"],
        default=DEFAULT_MODEL_VERSION,
        help=f"MinerU model version (default: {DEFAULT_MODEL_VERSION}).",
    )
    parser.add_argument(
        "--lang",
        default=DEFAULT_LANGUAGE,
        help=f"Language code (default: {DEFAULT_LANGUAGE}).",
    )
    parser.add_argument("--images", action="store_true", help="Keep extracted images/ directory.")
    parser.add_argument("--ocr", action="store_true", help="Enable OCR.")

    parser.set_defaults(enable_table=True, enable_formula=True)
    parser.add_argument(
        "--table", dest="enable_table", action="store_true", help="Enable table recognition."
    )
    parser.add_argument(
        "--no-table", dest="enable_table", action="store_false", help="Disable table recognition."
    )
    parser.add_argument(
        "--formula",
        dest="enable_formula",
        action="store_true",
        help="Enable formula recognition.",
    )
    parser.add_argument(
        "--no-formula",
        dest="enable_formula",
        action="store_false",
        help="Disable formula recognition.",
    )
    parser.add_argument(
        "--page-ranges",
        help='Page ranges to process, for example: "2,4-6".',
    )
    parser.add_argument("--proxy", help="HTTP(S) proxy URL.")
    parser.add_argument("--keep-zip", action="store_true", help="Keep downloaded zip file.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose logs.")
    return parser


def setup_logger(verbose: bool) -> None:
    """Configure loguru to write logs to stderr."""

    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG" if verbose else "INFO",
        format="{time:HH:mm:ss} | {level} | {message}",
    )


def prepare_output_dir(input_pdf: Path, out_dir: str | None) -> Path:
    """Resolve and create the output directory."""

    output_dir = Path(out_dir).expanduser() if out_dir else input_pdf.parent
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PTMError(
            f"Cannot create output directory: {output_dir}",
            f"Check path permissions and try again. Details: {exc}",
        ) from exc
    return output_dir.resolve()


def build_output_name(input_pdf: Path) -> str:
    """Build the timestamped output base name."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{input_pdf.stem}_PTM_{timestamp}"


def convert_pdf_via_api(args: argparse.Namespace) -> Path:
    """Run the full PDF-to-Markdown conversion flow."""

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


def main() -> int:
    """CLI entry point."""

    args = build_parser().parse_args()
    setup_logger(args.verbose)

    try:
        output_path = convert_pdf_via_api(args)
    except PTMError as exc:
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

    print(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
