#!/usr/bin/env -S uv run python
"""PyBits 工具日志路径回归检查。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _shared.utils.logging import _candidate_logs_dirs


class LoggingPathTests(unittest.TestCase):
    def test_install_origin_tool_logs_precede_installed_package_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            install_origin = root / "PyBits"
            installed_logs_dir = root / "site-packages" / "PTP" / "logs"

            with patch("_shared.utils.logging._install_origin", return_value=install_origin):
                candidates = _candidate_logs_dirs("ptp", installed_logs_dir)

            self.assertEqual(
                candidates,
                [
                    install_origin / "PTP" / "logs",
                    installed_logs_dir,
                ],
            )

    def test_external_cwd_is_not_used_as_log_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            cwd = root / "external"
            installed_logs_dir = root / "site-packages" / "PTP" / "logs"
            cwd.mkdir()

            with (
                patch("_shared.utils.logging._install_origin", return_value=None),
                patch("pathlib.Path.cwd", return_value=cwd),
            ):
                candidates = _candidate_logs_dirs("ptp", installed_logs_dir)

            self.assertEqual(candidates, [installed_logs_dir])
            self.assertNotIn(cwd / ".pybits" / "logs" / "ptp", candidates)


if __name__ == "__main__":
    sys.exit(unittest.main())
