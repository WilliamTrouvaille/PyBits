"""Tests for SKILLS utility functions."""

import tempfile
import unittest
from pathlib import Path

from src.utils import recursive_find_skills


class RecursiveFindSkillsTests(unittest.TestCase):
    def test_prefers_root_skills_directory_over_root_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "SKILL.md").write_text(
                "---\n"
                "name: root-skill\n"
                "description: Root wrapper skill\n"
                "---\n",
                encoding="utf-8",
            )

            nested_skill = root / "skills" / "writing-core"
            nested_skill.mkdir(parents=True)
            (nested_skill / "SKILL.md").write_text(
                "---\n"
                "name: writing-core\n"
                "description: Nested writing skill\n"
                "---\n",
                encoding="utf-8",
            )

            skill_dirs = recursive_find_skills(root)

        self.assertEqual(skill_dirs, [nested_skill])

    def test_skips_directory_symlinks_to_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = root / "deep-research"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: deep-research\n"
                "description: Test skill\n"
                "---\n",
                encoding="utf-8",
            )

            symlink_parent = root / "skills"
            symlink_parent.mkdir()
            symlink_path = symlink_parent / "deep-research"
            symlink_path.symlink_to(skill_dir, target_is_directory=True)

            skill_dirs = recursive_find_skills(root)

        self.assertEqual(skill_dirs, [skill_dir])


if __name__ == "__main__":
    unittest.main()
