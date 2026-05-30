"""Command-line entry point for CTA."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="CTA",
        description="Create AGENTS.md from CLAUDE.md in the current directory.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite AGENTS.md if it already exists.",
    )
    return parser


def convert_content(content: str) -> str:
    return content.replace("Claude", "Codex").replace(".claude/", ".codex/")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cwd = Path.cwd()
    source_path = cwd / "CLAUDE.md"
    target_path = cwd / "AGENTS.md"

    if not source_path.is_file():
        print(f"ERROR: CLAUDE.md not found in {cwd}", file=sys.stderr)
        return 1
    if target_path.exists() and not args.force:
        print(
            f"ERROR: AGENTS.md already exists in {cwd}; rerun with --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    content = source_path.read_text(encoding="utf-8")
    target_path.write_text(convert_content(content), encoding="utf-8")
    print(f"Created {target_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
