"""
SKILLS 命令行入口。
"""

from __future__ import annotations

import sys

from _shared.utils.logging import setup_tool_logger

from .src.cli_parser import build_parser
from .src.project_root import find_skills_project_root
from .src.utils import get_effective_paths, load_settings


def main(argv: list[str] | None = None) -> int:
    """
    运行 SKILLS 命令行接口。

    Args:
        argv: 可选的参数列表；为 None 时使用 sys.argv。

    Returns:
        进程退出码。
    """
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8")

    project_root = find_skills_project_root()
    settings = load_settings(project_root / "setting.yaml")
    paths = get_effective_paths(settings, project_root)

    setup_tool_logger(
        "SKILLS",
        logs_dir=paths["logs_dir"],
        retention_days=settings.log_retention_days,
        console_level=settings.log_level,
    )

    parser = build_parser(list(settings.agents))
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    try:
        return args.func(args, settings, paths)
    except KeyboardInterrupt:
        print("操作已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
