"""检查稀疏 launchd-like PATH 下的 Codex CLI 发现逻辑。"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from pathlib import Path

from HELLO.src.probe_env import build_codex_probe_env
from HELLO.src.process import get_version


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def main() -> int:
    original_env = os.environ.copy()
    try:
        with tempfile.TemporaryDirectory(prefix="hello-codex-env-") as td:
            home = Path(td)
            codex_dir = home / "codex-bin"
            codex_dir.mkdir(parents=True)

            write_executable(
                codex_dir / "codex",
                "\n".join(
                    [
                        "#!/bin/sh",
                        'if [ "$1" = "--version" ]; then',
                        "  echo 'codex fake 1.0'",
                        "  exit 0",
                        "fi",
                        "exit 1",
                        "",
                    ]
                ),
            )

            os.environ.clear()
            os.environ.update(
                {
                    "HOME": str(home),
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                }
            )

            env, checked_dirs = build_codex_probe_env(fallback_dirs=[codex_dir])
            exe = shutil.which("codex", path=env["PATH"])

            assert exe == str(codex_dir / "codex")
            assert str(codex_dir) in checked_dirs
            assert get_version(exe, [["--version"]], env=env) == "codex fake 1.0"
    finally:
        os.environ.clear()
        os.environ.update(original_env)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
