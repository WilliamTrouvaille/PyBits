#!/usr/bin/env -S uv run python
"""PyBits 子项目基本信息检验脚本。"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

TOOL_NAME_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")
PY_FILE_NAME_RE = re.compile(
    r"^(?:[a-z][a-z0-9]*(?:_[a-z0-9]+)*|__[a-z][a-z0-9]*(?:_[a-z0-9]+)*__)\.py$"
)

IGNORED_TOP_LEVEL_DIRS = {
    "__pycache__",
    "build",
    "dist",
}

REQUIRED_CHILDREN = {
    "README.md": "file",
    "cli.py": "file",
    "src": "dir",
}

OPTIONAL_CHILDREN = {
    ".env": "file",
    "setting.yaml": "file",
    "logs": "dir",
    "tests": "dir",
}

ALLOWED_CHILDREN = set(REQUIRED_CHILDREN) | set(OPTIONAL_CHILDREN)
SKIPPED_PY_DIR_NAMES = {"__pycache__", "logs"}


@dataclass(frozen=True)
class Failure:
    tool_name: str
    path: Path
    message: str


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def is_candidate_tool_dir(path: Path) -> bool:
    name = path.name
    if not path.is_dir():
        return False
    if name.startswith(".") or name.startswith("_"):
        return False
    if name in IGNORED_TOP_LEVEL_DIRS or name.endswith(".egg-info"):
        return False
    return any((path / child).exists() for child in ("README.md", "cli.py", "src")) or any(
        path.glob("*.py")
    )


def discover_tool_dirs(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.iterdir() if is_candidate_tool_dir(path)),
        key=lambda path: path.name,
    )


def expected_type_matches(path: Path, expected_type: str) -> bool:
    if expected_type == "file":
        return path.is_file()
    if expected_type == "dir":
        return path.is_dir()
    raise ValueError(f"未知路径类型: {expected_type}")


def check_tool_name(tool_dir: Path) -> list[Failure]:
    if TOOL_NAME_RE.fullmatch(tool_dir.name):
        return []
    return [
        Failure(
            tool_name=tool_dir.name,
            path=tool_dir,
            message="子项目目录名必须使用 UPPER-KEBAB-CASE",
        )
    ]


def check_required_children(tool_dir: Path) -> list[Failure]:
    failures: list[Failure] = []
    for child_name, expected_type in REQUIRED_CHILDREN.items():
        child = tool_dir / child_name
        if not child.exists():
            failures.append(
                Failure(
                    tool_name=tool_dir.name,
                    path=child,
                    message=f"缺少必需{expected_type}: {child_name}",
                )
            )
            continue
        if not expected_type_matches(child, expected_type):
            failures.append(
                Failure(
                    tool_name=tool_dir.name,
                    path=child,
                    message=f"{child_name} 必须是 {expected_type}",
                )
            )
    return failures


def check_optional_children(tool_dir: Path) -> list[Failure]:
    failures: list[Failure] = []
    for child_name, expected_type in OPTIONAL_CHILDREN.items():
        child = tool_dir / child_name
        if child.exists() and not expected_type_matches(child, expected_type):
            failures.append(
                Failure(
                    tool_name=tool_dir.name,
                    path=child,
                    message=f"可选路径 {child_name} 若存在则必须是 {expected_type}",
                )
            )
    return failures


def check_unexpected_direct_children(tool_dir: Path) -> list[Failure]:
    failures: list[Failure] = []
    for child in sorted(tool_dir.iterdir(), key=lambda path: path.name):
        if child.name in ALLOWED_CHILDREN:
            continue
        if child.is_dir():
            if not child.name.startswith("_"):
                failures.append(
                    Failure(
                        tool_name=tool_dir.name,
                        path=child,
                        message="非标准目录必须使用 `_` 前缀",
                    )
                )
            continue
        if child.is_file():
            if not child.name.startswith("."):
                failures.append(
                    Failure(
                        tool_name=tool_dir.name,
                        path=child,
                        message="非标准文件必须使用 `.` 前缀",
                    )
                )
            continue
        failures.append(
            Failure(
                tool_name=tool_dir.name,
                path=child,
                message="非标准路径必须是普通文件或目录，并遵守前缀规则",
            )
        )
    return failures


def should_skip_py_file(py_file: Path, tool_dir: Path) -> bool:
    relative_parts = py_file.relative_to(tool_dir).parts[:-1]
    return any(
        part in SKIPPED_PY_DIR_NAMES or part.startswith(".") or part.startswith("_")
        for part in relative_parts
    )


def check_python_file_names(tool_dir: Path) -> list[Failure]:
    failures: list[Failure] = []
    for py_file in sorted(tool_dir.rglob("*.py")):
        if should_skip_py_file(py_file, tool_dir):
            continue
        if PY_FILE_NAME_RE.fullmatch(py_file.name):
            continue
        failures.append(
            Failure(
                tool_name=tool_dir.name,
                path=py_file,
                message="Python 文件名必须使用 snake_case.py 或标准 dunder 模块名",
            )
        )
    return failures


def check_tool_dir(tool_dir: Path) -> list[Failure]:
    failures: list[Failure] = []
    failures.extend(check_tool_name(tool_dir))
    failures.extend(check_required_children(tool_dir))
    failures.extend(check_optional_children(tool_dir))
    failures.extend(check_unexpected_direct_children(tool_dir))
    failures.extend(check_python_file_names(tool_dir))
    return failures


def print_failure(failure: Failure, root: Path) -> None:
    print(f"[FAIL] {failure.tool_name}: {failure.message} -> {relative_path(failure.path, root)}")


def main() -> int:
    root = project_root()
    tool_dirs = discover_tool_dirs(root)

    print("== PyBits 基本信息检验 ==")
    print(f"项目根目录: {root}")
    print(f"发现子项目: {', '.join(path.name for path in tool_dirs) or '(无)'}")
    print()

    failures: list[Failure] = []
    if not tool_dirs:
        print("[FAIL] 未发现任何子项目目录")
        return 1

    for tool_dir in tool_dirs:
        failures.extend(check_tool_dir(tool_dir))

    if failures:
        for failure in failures:
            print_failure(failure, root)
        print()
        print(f"检验未通过: 共 {len(failures)} 项失败")
        return 1

    print("[PASS] 所有子项目结构和命名检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
