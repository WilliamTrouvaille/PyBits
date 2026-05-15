"""CLI entry point for backward compatibility."""

from ..cli import main

if __name__ == "__main__":
    raise SystemExit(main())
