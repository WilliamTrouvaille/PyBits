#!/usr/bin/env -S uv run python
"""SKILLS 最近安装记录与交互显示回归检查。"""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from questionary import Choice, Separator

from SKILLS.src import project_root as skills_project_root
from SKILLS.src.commands.install import (
    build_install_source_choices,
    format_skill_label,
    handle_install,
    resolve_recent_skill,
)
from SKILLS.src.installer import InstallResult
from SKILLS.src.models import Repository, RepositoryType, Skill
from SKILLS.src.recent import RecentSkillRef, load_recent, load_recent_refs, record_recent
from SKILLS.src.utils import Settings, get_effective_paths


def make_repo(name: str) -> Repository:
    return Repository(
        name=name,
        type=RepositoryType.LOCAL,
        url=None,
        path=Path(f"/tmp/{name}"),
        local_path=None,
        registered_at=datetime(2026, 1, 1),
    )


class SkillsRecentInstallCheck(unittest.TestCase):
    def test_record_recent_preserves_repository_and_keeps_name_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            recent_path = Path(temp_dir) / ".recent_installs.local.json"
            legacy_path = Path(temp_dir) / ".recent_installs.json"
            legacy_path.write_text(
                json.dumps({"skills": ["shared-skill"]}),
                encoding="utf-8",
            )

            record_recent("shared-skill", recent_path, "repo-b")

            raw_data = json.loads(recent_path.read_text(encoding="utf-8"))
            self.assertEqual(
                raw_data["skills"],
                [{"name": "shared-skill", "repository_name": "repo-b"}],
            )
            self.assertEqual(load_recent(recent_path), ["shared-skill"])
            self.assertEqual(load_recent_refs(recent_path)[0].repository_name, "repo-b")
            self.assertTrue(recent_path.is_file())

    def test_resolve_recent_skill_prefers_recorded_repository_quietly(self) -> None:
        repos = [make_repo("repo-a"), make_repo("repo-b")]
        skills_by_repo = {
            "repo-a": [Skill("shared-skill", "from repo a", Path("/tmp/repo-a/shared"), "repo-a")],
            "repo-b": [Skill("shared-skill", "from repo b", Path("/tmp/repo-b/shared"), "repo-b")],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            recent_path = Path(temp_dir) / ".recent_installs.local.json"
            record_recent("shared-skill", recent_path, "repo-b")

            with patch(
                "SKILLS.src.commands.install.scan_repository",
                side_effect=lambda repo, *_args, **_kwargs: skills_by_repo[repo.name],
            ) as scan_repository:
                recent_skill = resolve_recent_skill(
                    load_recent_refs(recent_path)[0],
                    repos,
                    Settings(),
                )

        self.assertIsNotNone(recent_skill)
        assert recent_skill is not None
        self.assertEqual(recent_skill.repository_name, "repo-b")
        self.assertEqual(recent_skill.description, "from repo b")
        scan_repository.assert_called_once()
        self.assertEqual(scan_repository.call_args.args[0].name, "repo-b")
        self.assertIs(scan_repository.call_args.kwargs["log_summary"], False)

    def test_first_prompt_lists_recent_skills_before_repositories(self) -> None:
        recent_ref = RecentSkillRef("first-skill", "repo-a")
        repo = make_repo("repo-z")

        with patch("SKILLS.src.commands.install.scan_repository") as scan_repository:
            choices = build_install_source_choices([repo], [recent_ref])
        selectable_choices = [
            choice
            for choice in choices
            if isinstance(choice, Choice) and not isinstance(choice, Separator)
        ]

        scan_repository.assert_not_called()
        self.assertIs(selectable_choices[0].value, recent_ref)
        self.assertEqual(selectable_choices[0].title, "  first-skill (repo-a)")
        self.assertIs(selectable_choices[1].value, repo)
        self.assertEqual(selectable_choices[1].title, "repo-z (local)")

        skill_label = format_skill_label(
            Skill("first-skill", "description", Path("/tmp/first"), "repo-a"),
            include_repository=True,
        )
        self.assertEqual(skill_label, "first-skill (repo-a) - description")

    def test_effective_paths_use_local_recent_file_name(self) -> None:
        root = Path("/tmp/project/SKILLS")
        paths = get_effective_paths(Settings(), root)

        self.assertEqual(paths["recent_installs_path"], root / ".recent_installs.local.json")
        self.assertEqual(paths["legacy_recent_installs_path"], root / ".recent_installs.json")

    def test_failed_install_does_not_record_recent(self) -> None:
        repo = make_repo("repo-a")
        skill = Skill("target-skill", "description", Path("/tmp/target"), "repo-a")
        args = argparse.Namespace(
            repository="repo-a",
            skills=["target-skill"],
            scope="user",
            agent="codex",
            mode="copy",
            project_dir=None,
            force=False,
        )
        paths = {
            "repos_json_path": Path("/tmp/repos.json"),
            "repos_local_json_path": Path("/tmp/repos.local.json"),
            "recent_installs_path": Path("/tmp/.recent_installs.local.json"),
        }

        with (
            patch("SKILLS.src.commands.install.get_repository", return_value=repo),
            patch("SKILLS.src.commands.install.scan_repository", return_value=[skill]),
            patch(
                "SKILLS.src.commands.install.install_skill",
                return_value=[
                    InstallResult(
                        skill_name="target-skill",
                        agent="codex",
                        target_path=Path("/tmp/target-skill"),
                        status="skipped",
                    )
                ],
            ),
            patch("SKILLS.src.commands.install.record_recent") as record_recent_mock,
        ):
            exit_code = handle_install(args, Settings(), paths)

        self.assertEqual(exit_code, 1)
        record_recent_mock.assert_not_called()

    def test_install_origin_finds_checkout_without_repos_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            checkout_root = Path(temp_dir) / "PyBits"
            skills_dir = checkout_root / "SKILLS"
            (skills_dir / "src").mkdir(parents=True)
            (skills_dir / "cli.py").write_text("", encoding="utf-8")
            (skills_dir / "README.md").write_text("# SKILLS\n", encoding="utf-8")

            class FakeDistribution:
                def read_text(self, name: str) -> str | None:
                    if name != "direct_url.json":
                        return None
                    return json.dumps({"url": checkout_root.as_uri()})

            with patch.object(
                skills_project_root.importlib_metadata,
                "distribution",
                return_value=FakeDistribution(),
            ):
                project_root = skills_project_root.find_project_root_from_install_origin()

        self.assertEqual(project_root, skills_dir.resolve())


if __name__ == "__main__":
    unittest.main()
