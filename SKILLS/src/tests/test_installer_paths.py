"""SKILLS 安装目标路径回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from SKILLS.src.installer import get_target_dir
from SKILLS.src.models import AgentType, ScopeType


class GetTargetDirTests(unittest.TestCase):
    def test_codex_project_scope_uses_agents_skills_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            (project_dir / ".agents").mkdir()

            target_dir = get_target_dir(
                AgentType.CODEX,
                ScopeType.PROJECT,
                project_dir,
            )

            self.assertEqual(target_dir, project_dir / ".agents" / "skills")
            self.assertTrue(target_dir.is_dir())

    def test_claude_project_scope_still_uses_claude_skills_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            (project_dir / "AGENTS.md").write_text("", encoding="utf-8")

            target_dir = get_target_dir(
                AgentType.CLAUDE,
                ScopeType.PROJECT,
                project_dir,
            )

            self.assertEqual(target_dir, project_dir / ".claude" / "skills")
            self.assertTrue(target_dir.is_dir())

    def test_codex_user_scope_uses_home_agents_skills_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_dir = Path(temp_dir)

            with patch("SKILLS.src.installer.Path.home", return_value=home_dir):
                target_dir = get_target_dir(AgentType.CODEX, ScopeType.USER)

            self.assertEqual(target_dir, home_dir / ".agents" / "skills")
            self.assertTrue(target_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
