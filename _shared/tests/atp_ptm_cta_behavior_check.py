#!/usr/bin/env -S uv run python
"""ATP、PTM、CTA 风险修复回归检查。"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from ATP.src import atp
from CTA.cli import main as cta_main
from PTM.src import api_client, file_handler
from PTM.src.models import PTMError
from PTM.src.workflow import _validate_runtime_options


class ATPBehaviorCheck(unittest.TestCase):
    def test_extract_figures_passes_proxy_to_arxiv_to_prompt(self) -> None:
        completed = Mock(returncode=0, stdout="", stderr="")

        with patch("ATP.src.atp.subprocess.run", return_value=completed) as run:
            result = atp.extract_figures(
                "1911.11763",
                Path("/tmp/cache"),
                Path("/tmp/out"),
                no_comments=True,
                no_appendix=False,
                proxy="http://127.0.0.1:7890",
            )

        self.assertEqual(result, [])
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["HTTP_PROXY"], "http://127.0.0.1:7890")
        self.assertEqual(env["HTTPS_PROXY"], "http://127.0.0.1:7890")

    def test_json_mode_stdout_contains_only_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cached_tex = root / "cached.tex"
            cached_tex.write_text("content", encoding="utf-8")
            out_dir = root / "out"
            args = argparse.Namespace(
                arxiv_input="1911.11763",
                out_dir=out_dir,
                json=True,
                force=False,
                proxy=None,
                no_comments=True,
                comments=False,
                figure_paths=True,
                no_figure_paths=True,
                no_appendix=False,
            )

            stdout = io.StringIO()
            with (
                patch("ATP.src.atp.check_arxiv_tool", return_value=True),
                patch("ATP.src.atp.check_cache", return_value=cached_tex),
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = atp.run_atp_workflow(args)

        self.assertEqual(exit_code, 0)
        self.assertTrue(stdout.getvalue().lstrip().startswith("{"))
        self.assertNotIn("OK", stdout.getvalue())
        self.assertNotIn("完成", stdout.getvalue())


class PTMBehaviorCheck(unittest.TestCase):
    def test_runtime_options_are_validated_before_network_work(self) -> None:
        args = argparse.Namespace(
            timeout=0,
            poll_interval=3,
            download_retries=4,
            download_backoff=2.0,
        )

        with self.assertRaises(PTMError):
            _validate_runtime_options(args)

    def test_request_errors_redact_urls(self) -> None:
        request = requests.Request("GET", "https://signed.example/path?token=secret").prepare()
        exc = requests.RequestException(
            "failed for https://signed.example/path?token=secret",
            request=request,
        )

        self.assertEqual(
            api_client._safe_request_error(exc),
            "failed for https://signed.example/[redacted]",
        )
        self.assertEqual(
            file_handler._safe_request_error(exc),
            "failed for https://signed.example/[redacted]",
        )


class CTABehaviorCheck(unittest.TestCase):
    def test_broken_target_symlink_requires_force(self) -> None:
        original_cwd = Path.cwd()
        original_argv = list(os.sys.argv)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                (root / "CLAUDE.md").write_text("Claude .claude/path", encoding="utf-8")
                (root / "AGENTS.md").symlink_to(root / "missing-target")
                os.chdir(root)
                os.sys.argv = ["CTA"]

                exit_code = cta_main()

            self.assertEqual(exit_code, 1)
        finally:
            os.chdir(original_cwd)
            os.sys.argv = original_argv


if __name__ == "__main__":
    unittest.main()
