"""Command-line entry point for AIM."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from _shared.utils.logging import setup_tool_logger

from .src.indexer import build_index, parse_since

LOGS_DIR = Path(__file__).parent / "logs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="AIM",
        description="Index Claude Code and Codex sessions into redacted candidate memories.",
    )
    parser.add_argument(
        "--claude-home",
        default="~/.claude",
        help="Claude Code home directory (default: ~/.claude).",
    )
    parser.add_argument(
        "--codex-home",
        default="~/.codex",
        help="Codex home directory (default: ~/.codex).",
    )
    parser.add_argument(
        "--since",
        help="Only include files modified after this date/time, e.g. 2026-05-01.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of evidence records to write (default: 100).",
    )
    parser.add_argument(
        "--out-dir",
        help="Output directory. Defaults to .codex/aim/{timestamp}.",
    )
    parser.add_argument("--json", action="store_true", help="Print a JSON summary.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose logs.")
    return parser


def default_out_dir() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.cwd() / ".codex" / "aim" / timestamp


def resolve_out_dir(raw_out_dir: str | None) -> Path:
    out_dir = Path(raw_out_dir).expanduser() if raw_out_dir else default_out_dir()
    index_path = out_dir / "index.json"
    candidates_path = out_dir / "candidates.md"
    if index_path.exists() or candidates_path.exists():
        raise ValueError(
            f"Output directory already contains AIM results: {out_dir}. "
            "Choose a new --out-dir."
        )
    return out_dir.resolve()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    setup_tool_logger("aim", logs_dir=LOGS_DIR, verbose=args.verbose, retention_days=30)

    if args.limit < 1:
        parser.error("--limit must be greater than 0")

    try:
        since = parse_since(args.since)
        out_dir = resolve_out_dir(args.out_dir)
        records = build_index(
            claude_home=Path(args.claude_home),
            codex_home=Path(args.codex_home),
            out_dir=out_dir,
            since=since,
            limit=args.limit,
        )
    except (OSError, ValueError) as exc:
        logger.error(str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = {
        "out_dir": str(out_dir),
        "index": str(out_dir / "index.json"),
        "candidates": str(out_dir / "candidates.md"),
        "records": len(records),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"AIM index written: {out_dir}")
        print(f"Records: {len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
