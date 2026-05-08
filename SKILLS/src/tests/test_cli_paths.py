"""SKILLS CLI 路径解析回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from SKILLS.src.cli import find_project_root_from_install_origin, find_skills_project_root


class FindSkillsProjectRootTests(unittest.TestCase):
    def test_finds_nested_skills_dir_from_workspace_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            skills_dir = workspace_root / "SKILLS"
            skills_dir.mkdir()
            (skills_dir / ".repos.json").write_text('{"repositories": []}', encoding="utf-8")

            with patch("SKILLS.src.cli.Path.cwd", return_value=workspace_root):
                self.assertEqual(find_skills_project_root(), skills_dir)

    def test_direct_repos_json_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir)
            (skills_dir / ".repos.json").write_text('{"repositories": []}', encoding="utf-8")
            nested_skills_dir = skills_dir / "SKILLS"
            nested_skills_dir.mkdir()
            (nested_skills_dir / ".repos.json").write_text('{"repositories": []}', encoding="utf-8")

            with patch("SKILLS.src.cli.Path.cwd", return_value=skills_dir):
                self.assertEqual(find_skills_project_root(), skills_dir)

    def test_finds_skills_dir_from_local_install_origin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            checkout_root = Path(temp_dir)
            skills_dir = checkout_root / "SKILLS"
            skills_dir.mkdir()
            (skills_dir / ".repos.json").write_text('{"repositories": []}', encoding="utf-8")
            distribution = StubDistribution(
                direct_url_text=f'{{"url": "{checkout_root.as_uri()}", "dir_info": {{}}}}'
            )

            with patch("SKILLS.src.cli.importlib_metadata.distribution", return_value=distribution):
                self.assertEqual(find_project_root_from_install_origin(), skills_dir)

    def test_ignores_non_file_install_origin(self) -> None:
        distribution = StubDistribution(
            direct_url_text='{"url": "https://example.com/pybits.git", "vcs_info": {}}'
        )

        with patch("SKILLS.src.cli.importlib_metadata.distribution", return_value=distribution):
            self.assertIsNone(find_project_root_from_install_origin())


class StubDistribution:
    def __init__(self, direct_url_text: str | None) -> None:
        self.direct_url_text = direct_url_text

    def read_text(self, filename: str) -> str | None:
        if filename == "direct_url.json":
            return self.direct_url_text
        return None


if __name__ == "__main__":
    unittest.main()
