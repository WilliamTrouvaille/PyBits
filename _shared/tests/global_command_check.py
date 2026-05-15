#!/usr/bin/env -S uv run python
"""PyBits 全局命令规范化检验脚本。"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

TOOL_NAME_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")
INLINE_DEPENDENCY_PATTERNS = (
    (re.compile(r"(?m)^#!.*\buv\s+run\s+--script\b"), "uv run --script shebang"),
    (re.compile(r"(?m)^#\s*///\s*script\s*$"), "PEP 723 inline script block"),
    (re.compile(r"(?m)^#\s*dependencies\s*="), "inline dependencies"),
    (re.compile(r"(?m)^#\s*requires-python\s*="), "inline requires-python"),
)

IGNORED_TOP_LEVEL_DIRS = {
    "__pycache__",
    "build",
    "dist",
}
SKIPPED_PY_DIR_NAMES = {"__pycache__", "logs"}


@dataclass(frozen=True)
class Failure:
    scope: str
    message: str
    detail: str = ""


@dataclass(frozen=True)
class CommandCase:
    name: str
    args: list[str]
    expect_success: bool
    timeout_seconds: int = 30


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


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


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def load_pyproject(root: Path) -> tuple[dict[str, Any] | None, Failure | None]:
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.is_file():
        return None, Failure("pyproject.toml", "缺少 pyproject.toml")
    try:
        with pyproject_path.open("rb") as file:
            return tomllib.load(file), None
    except tomllib.TOMLDecodeError as exc:
        return None, Failure("pyproject.toml", "pyproject.toml 解析失败", str(exc))


def validate_pyproject_tables(pyproject: dict[str, Any]) -> list[Failure]:
    failures: list[Failure] = []
    project = pyproject.get("project")
    if not isinstance(project, dict):
        return [Failure("pyproject.toml", "缺少 [project] 表")]

    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list):
        failures.append(
            Failure(
                "pyproject.toml",
                "[project].dependencies 必须存在且使用列表统一声明依赖",
            )
        )

    scripts = project.get("scripts")
    if not isinstance(scripts, dict) or not scripts:
        failures.append(Failure("pyproject.toml", "缺少非空的 [project.scripts] 全局命令声明"))
    elif any(not isinstance(value, str) for value in scripts.values()):
        failures.append(Failure("pyproject.toml", "[project.scripts] 的所有入口值必须是字符串"))

    return failures


def scripts_from_pyproject(pyproject: dict[str, Any]) -> dict[str, str]:
    project = pyproject.get("project")
    if not isinstance(project, dict):
        return {}
    scripts = project.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {str(command): target for command, target in scripts.items() if isinstance(target, str)}


def validate_tool_scripts(tool_dirs: list[Path], scripts: dict[str, str]) -> list[Failure]:
    failures: list[Failure] = []
    for tool_dir in tool_dirs:
        tool_name = tool_dir.name
        if not TOOL_NAME_RE.fullmatch(tool_name):
            failures.append(
                Failure(
                    tool_name,
                    "子项目目录名不符合 UPPER-KEBAB-CASE，无法作为标准全局命令名",
                )
            )
        target = scripts.get(tool_name)
        if target is None:
            failures.append(
                Failure(
                    tool_name,
                    f"缺少 [project.scripts].{tool_name} 全局命令声明",
                )
            )
            continue
        if ":" not in target:
            failures.append(
                Failure(tool_name, "全局命令入口必须使用 `module:function` 格式", target)
            )
            continue
        module_name, function_name = target.split(":", 1)
        if not module_name or not function_name:
            failures.append(Failure(tool_name, "全局命令入口 module 或 function 不能为空", target))
    return failures


def should_skip_py_file(py_file: Path, tool_dir: Path) -> bool:
    relative_parts = py_file.relative_to(tool_dir).parts[:-1]
    return any(
        part in SKIPPED_PY_DIR_NAMES or part.startswith(".") or part.startswith("_")
        for part in relative_parts
    )


def find_inline_dependency_blocks(tool_dirs: list[Path], root: Path) -> list[Failure]:
    failures: list[Failure] = []
    for tool_dir in tool_dirs:
        for py_file in sorted(tool_dir.rglob("*.py")):
            if should_skip_py_file(py_file, tool_dir):
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                failures.append(
                    Failure(
                        tool_dir.name,
                        "Python 文件必须可用 UTF-8 读取以检查 inline dependency",
                        f"{relative_path(py_file, root)}: {exc}",
                    )
                )
                continue
            for pattern, label in INLINE_DEPENDENCY_PATTERNS:
                if pattern.search(content):
                    failures.append(
                        Failure(
                            tool_dir.name,
                            "脚本内不得使用 inline dependency 块",
                            f"{relative_path(py_file, root)}: {label}",
                        )
                    )
    return failures


def format_command(args: list[str]) -> str:
    return " ".join(args)


def command_failure_detail(
    args: list[str],
    cwd: Path,
    returncode: int | str,
    stdout: str | bytes | None,
    stderr: str | bytes | None,
) -> str:
    def normalize(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    normalized_stdout = normalize(stdout).rstrip()
    normalized_stderr = normalize(stderr).rstrip()
    return "\n".join(
        (
            f"命令: {format_command(args)}",
            f"工作目录: {cwd}",
            f"退出码: {returncode}",
            "--- stdout ---",
            normalized_stdout or "(空)",
            "--- stderr ---",
            normalized_stderr or "(空)",
        )
    )


def run_command_case(
    command: str,
    case: CommandCase,
    cwd: Path,
) -> Failure | None:
    args = [command, *case.args]
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=case.timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        return Failure(
            command,
            f"外部环境测试 `{case.name}` 未找到全局命令",
            command_failure_detail(args, cwd, "FileNotFoundError", "", str(exc)),
        )
    except subprocess.TimeoutExpired as exc:
        return Failure(
            command,
            f"外部环境测试 `{case.name}` 超时",
            command_failure_detail(args, cwd, "timeout", exc.stdout, exc.stderr),
        )

    passed = completed.returncode == 0 if case.expect_success else completed.returncode != 0
    if passed:
        print(f"[PASS] {command}: {case.name} -> exit {completed.returncode} ({cwd})")
        return None

    expectation = "退出码应为 0" if case.expect_success else "退出码应为非 0"
    return Failure(
        command,
        f"外部环境测试 `{case.name}` 失败: {expectation}",
        command_failure_detail(
            args,
            cwd,
            completed.returncode,
            completed.stdout,
            completed.stderr,
        ),
    )


def run_install(root: Path) -> Failure | None:
    args = ["uv", "tool", "install", "--force", "--reinstall", "--refresh", "."]
    print(f"[RUN] {format_command(args)}")
    try:
        completed = subprocess.run(
            args,
            cwd=root,
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
    except FileNotFoundError as exc:
        return Failure(
            "uv tool install",
            "刷新已安装工具失败: 未找到 uv",
            command_failure_detail(args, root, "FileNotFoundError", "", str(exc)),
        )
    except subprocess.TimeoutExpired as exc:
        return Failure(
            "uv tool install",
            "刷新已安装工具超时",
            command_failure_detail(args, root, "timeout", exc.stdout, exc.stderr),
        )

    if completed.returncode == 0:
        print("[PASS] uv tool install 刷新成功")
        return None

    return Failure(
        "uv tool install",
        "刷新已安装工具失败",
        command_failure_detail(
            args,
            root,
            completed.returncode,
            completed.stdout,
            completed.stderr,
        ),
    )


def external_test_dir(tool_name: str, timestamp: str) -> Path:
    return Path.home() / "TEMP" / "pybits_tests" / f"TEST-{tool_name}-{timestamp}"


def run_external_command_tests(
    tool_dirs: list[Path],
    scripts: dict[str, str],
    install_ok: bool,
) -> list[Failure]:
    failures: list[Failure] = []
    if not install_ok:
        for tool_dir in tool_dirs:
            if tool_dir.name in scripts:
                failures.append(
                    Failure(
                        tool_dir.name,
                        "跳过外部环境测试: uv tool install 未通过，不能验证最新全局命令",
                    )
                )
        return failures

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cases = (
        CommandCase(name="基本功能 --help", args=["--help"], expect_success=True),
        CommandCase(
            name="错误处理: 未知参数",
            args=["--__pybits_invalid_option__"],
            expect_success=False,
        ),
    )

    for tool_dir in tool_dirs:
        command = tool_dir.name
        if command not in scripts:
            continue
        test_dir = external_test_dir(command, timestamp)
        try:
            test_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            failures.append(Failure(command, "无法创建外部环境测试目录", f"{test_dir}: {exc}"))
            continue
        for case in cases:
            failure = run_command_case(command, case, test_dir)
            if failure is not None:
                failures.append(failure)
    return failures


def print_failure(failure: Failure) -> None:
    print(f"[FAIL] {failure.scope}: {failure.message}")
    if failure.detail:
        print(failure.detail)


def main() -> int:
    root = project_root()
    print("== PyBits 全局命令规范化检验 ==")
    print(f"项目根目录: {root}")
    print()

    install_failure = run_install(root)
    print()

    tool_dirs = discover_tool_dirs(root)
    print(f"发现子项目: {', '.join(path.name for path in tool_dirs) or '(无)'}")

    failures: list[Failure] = []
    if install_failure is not None:
        failures.append(install_failure)

    pyproject, load_failure = load_pyproject(root)
    if load_failure is not None:
        failures.append(load_failure)
        pyproject = {}

    failures.extend(validate_pyproject_tables(pyproject))
    scripts = scripts_from_pyproject(pyproject)
    failures.extend(validate_tool_scripts(tool_dirs, scripts))
    failures.extend(find_inline_dependency_blocks(tool_dirs, root))
    failures.extend(
        run_external_command_tests(
            tool_dirs,
            scripts,
            install_ok=install_failure is None,
        )
    )

    print()
    if failures:
        for failure in failures:
            print_failure(failure)
            print()
        print(f"检验未通过: 共 {len(failures)} 项失败")
        return 1

    print("[PASS] 全局命令规范化检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
