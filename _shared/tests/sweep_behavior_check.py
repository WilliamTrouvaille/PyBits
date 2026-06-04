#!/usr/bin/env -S uv run python
"""SWEEP fixture 行为检查。"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from SWEEP.cli import _move_candidates
from SWEEP.src.config import load_config, resolve_trash_command
from SWEEP.src.models import (
    CandidateGroup,
    CandidateKind,
    CleanupCandidate,
    ExecutionSummary,
    ScopeType,
)
from SWEEP.src.trash_runner import TrashAvailability

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path.home() / "TEMP" / "pybits_tests"


def main() -> int:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = TEST_ROOT / f"SWEEP-FIXTURE-{timestamp}"
    base.mkdir(parents=True, exist_ok=True)
    _resolve_previous_fixture_manifest_entries()

    print("== SWEEP fixture 行为检查 ==")
    print(f"fixture 路径: {base}")

    fake_trash = _write_fake_trash(base)
    fixture = _build_scan_fixture(base)
    config_path = _write_config(base, fake_trash, fixture["fake_trash_dir"])

    dry_run = _run_sweep(["--dry-run", "--json", "--config", str(config_path)], cwd=base)
    _assert_ok(dry_run, "dry-run fixture 扫描")
    dry_summary = _load_json(dry_run.stdout)
    _assert_candidate(dry_summary, fixture["system_old_file"], "partial_items")
    _assert_candidate(dry_summary, fixture["download_old_file"], "partial_items")
    _assert_candidate(dry_summary, fixture["project_tmp"], "whole_dir")
    _assert_candidate(dry_summary, fixture["project_codex_old_file"], "partial_items")
    _assert_no_candidate(dry_summary, fixture["system_new_file"])
    _assert_no_candidate(dry_summary, fixture["download_old_dir"])
    _assert_no_candidate(dry_summary, fixture["trash_bin_root"])
    _assert_no_candidate(dry_summary, fixture["symlink_path"])
    print("[PASS] dry-run 候选和安全跳过检查")

    dry_run_cached = _run_sweep(["--dry-run", "--json", "--config", str(config_path)], cwd=base)
    _assert_ok(dry_run_cached, "dry-run 缓存命中")
    cached_summary = _load_json(dry_run_cached.stdout)
    if cached_summary["cache"]["cache_hits"] < 1:
        raise AssertionError("第二次运行应命中项目 Watch Dir 缓存")
    print("[PASS] 第二次运行命中缓存")

    _poison_project_watch_dir_cache(fixture["project_unauthorized_dir"])
    poisoned_cache_run = _run_sweep(["--dry-run", "--json", "--config", str(config_path)], cwd=base)
    _assert_ok(poisoned_cache_run, "污染缓存后的刷新")
    poisoned_summary = _load_json(poisoned_cache_run.stdout)
    _assert_no_candidate(poisoned_summary, fixture["project_unauthorized_dir"])
    _assert_no_candidate(poisoned_summary, fixture["project_unauthorized_old_file"])
    print("[PASS] 缓存拒绝未授权 Watch Dir")

    _assert_move_candidates_revalidates_before_trash(config_path, fixture)

    real_run = _run_sweep(["--json", "--config", str(config_path)], cwd=base)
    _assert_ok(real_run, "fake-trash real run")
    real_summary = _load_json(real_run.stdout)
    if real_summary["execution"]["trash_unavailable"]:
        raise AssertionError("fixture trash 命令应当可用")
    if len(real_summary["execution"]["moved"]) < 1:
        raise AssertionError("fixture trash 应当移动候选")
    if fixture["system_old_file"].exists():
        raise AssertionError("过期系统临时文件应当被移动")
    print("[PASS] fixture trash 真实移动")

    empty_run = _run_sweep(["--dry-run", "--json", "--config", str(config_path)], cwd=base)
    _assert_ok(empty_run, "清理后空候选 dry-run")
    empty_summary = _load_json(empty_run.stdout)
    if empty_summary["candidate_counts"]["total"] != 0:
        raise AssertionError("真实移动后不应再产生候选")
    print("[PASS] 无候选后续运行仍写摘要")

    fallback_config, fallback_file = _build_fallback_fixture(base)
    fallback_run = _run_sweep(["--json", "--config", str(fallback_config)], cwd=base)
    _assert_ok(fallback_run, "trash 不可用时 fallback")
    fallback_summary = _load_json(fallback_run.stdout)
    if not fallback_summary["execution"]["trash_unavailable"]:
        raise AssertionError("fallback 运行应标记 trash_unavailable")
    if fallback_file.exists():
        raise AssertionError("fallback 源文件应当被移动")
    print("[PASS] trash 不可用时 soft-delete fallback")

    unresolved_config, unresolved_file, blocked_path, block_file = _build_unresolved_fixture(base)
    unresolved_run = _run_sweep(["--json", "--config", str(unresolved_config)], cwd=base)
    if unresolved_run.returncode == 0:
        raise AssertionError("unresolved 运行应返回非零退出码")
    unresolved_summary = _load_json(unresolved_run.stdout)
    if len(unresolved_summary["execution"]["unresolved"]) != 1:
        raise AssertionError("应产生一个 unresolved 失败")

    _append_manual_blocked_unresolved(blocked_path)
    unresolved_dry_run = _run_sweep(
        ["--dry-run", "--json", "--config", str(unresolved_config)],
        cwd=base,
    )
    _assert_ok(unresolved_dry_run, "unresolved dry-run")
    unresolved_dry_summary = _load_json(unresolved_dry_run.stdout)
    retry_count = unresolved_dry_summary["candidate_counts"]["retry_unresolved"]
    blocked_count = len(unresolved_dry_summary["blocked_unresolved"])
    if retry_count < 1 or blocked_count < 1:
        raise AssertionError("dry-run 应展示可重试和被阻塞的 unresolved 项")
    print("[PASS] unresolved 重试和被阻塞项 dry-run 展示")

    _append_manual_resolved(blocked_path)
    block_file.rename(block_file.with_name("fallback-blocker-moved"))
    block_file.mkdir(parents=True, exist_ok=True)
    resolved_run = _run_sweep(["--json", "--config", str(unresolved_config)], cwd=base)
    _assert_ok(resolved_run, "通过 fallback 解决 unresolved")
    if unresolved_file.exists():
        raise AssertionError("unresolved 文件应通过 fallback 解决")
    print("[PASS] unresolved manifest 重试和解决")

    outside_cwd = base / "outside_cwd"
    outside_cwd.mkdir(parents=True, exist_ok=True)
    outside_run = _run_sweep(
        ["--dry-run", "--json", "--config", str(config_path)],
        cwd=outside_cwd,
    )
    _assert_ok(outside_run, "项目外目录 dry-run")
    print("[PASS] 项目外目录 dry-run 调用")

    print("[PASS] SWEEP fixture 行为检查完成")
    return 0


def _write_fake_trash(base: Path) -> Path:
    fake_trash_dir = base / "fake_trash"
    fake_trash_dir.mkdir(parents=True, exist_ok=True)
    script = base / "fake_trash.sh"
    script.write_text(
        """#!/bin/sh
dest="$1"
shift
mkdir -p "$dest" || exit 1
i=0
for path in "$@"; do
  i=$((i + 1))
  base_name=$(basename "$path")
  mv "$path" "$dest/$$_${i}_${base_name}" || exit 1
done
""",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def _build_scan_fixture(base: Path) -> dict[str, Path]:
    old_time = datetime.now() - timedelta(days=40)
    system_dir = base / "system_temp"
    downloads_dir = base / "downloads"
    code_dir = base / "CODE"
    for directory in (system_dir, downloads_dir, code_dir):
        directory.mkdir(parents=True, exist_ok=True)

    system_old_file = system_dir / "old.tmp"
    system_new_file = system_dir / "new.tmp"
    system_old_file.write_text("old", encoding="utf-8")
    system_new_file.write_text("new", encoding="utf-8")
    _touch_old(system_old_file, old_time)

    symlink_path = system_dir / "old-link.tmp"
    try:
        symlink_path.symlink_to(system_old_file)
    except OSError:
        symlink_path.write_text("symlink 不可用", encoding="utf-8")

    download_old_dir = downloads_dir / "old_dir"
    download_old_dir.mkdir()
    download_old_file = download_old_dir / "old-download.tmp"
    download_old_file.write_text("old", encoding="utf-8")
    _touch_old(download_old_file, old_time)
    _touch_old(download_old_dir, old_time)

    project = code_dir / "demo_project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    project_unauthorized_dir = project / "not_temp"
    project_unauthorized_dir.mkdir()
    project_unauthorized_old_file = project_unauthorized_dir / "old-unauthorized.tmp"
    project_unauthorized_old_file.write_text("old", encoding="utf-8")
    _touch_tree_old(project_unauthorized_dir, old_time)

    project_tmp = project / "tmp"
    project_tmp.mkdir()
    (project_tmp / "old.txt").write_text("old", encoding="utf-8")
    _touch_tree_old(project_tmp, old_time)

    codex_tmp = project / ".codex" / "tmp"
    codex_tmp.mkdir(parents=True)
    project_codex_old_file = codex_tmp / "trace.tmp.data"
    project_codex_old_file.write_text("old", encoding="utf-8")
    (codex_tmp / "new.txt").write_text("new", encoding="utf-8")
    _touch_old(project_codex_old_file, old_time)

    trash_bin_root = project / ".codex" / "_trash_bin_"
    trash_bin_root.mkdir(parents=True)
    trash_payload = trash_bin_root / "old_payload"
    trash_payload.write_text("old", encoding="utf-8")
    _touch_old(trash_payload, old_time)
    _touch_old(trash_bin_root, old_time)

    return {
        "system_dir": system_dir,
        "downloads_dir": downloads_dir,
        "code_dir": code_dir,
        "project": project,
        "system_old_file": system_old_file,
        "system_new_file": system_new_file,
        "download_old_dir": download_old_dir,
        "download_old_file": download_old_file,
        "project_tmp": project_tmp,
        "project_codex_old_file": project_codex_old_file,
        "trash_bin_root": trash_bin_root,
        "project_unauthorized_dir": project_unauthorized_dir,
        "project_unauthorized_old_file": project_unauthorized_old_file,
        "symlink_path": symlink_path,
        "fake_trash_dir": base / "fake_trash",
    }


def _write_config(base: Path, trash_command: Path, fake_trash_dir: Path) -> Path:
    config_path = base / "sweep_fixture.yaml"
    config_path.write_text(
        f"""
system_temp:
  dirs:
    - "{base / "system_temp"}"
  keep_days: 15
downloads:
  dirs:
    - "{base / "downloads"}"
  keep_days: 30
projects:
  roots:
    - "{base / "CODE"}"
  keep_days: 7
trash:
  command:
    - "{trash_command}"
    - "{fake_trash_dir}"
  workers: 1
  retries: 0
scan:
  workers: 1
  max_depth: 4
""".lstrip(),
        encoding="utf-8",
    )
    return config_path


def _build_fallback_fixture(base: Path) -> tuple[Path, Path]:
    root = base / "fallback_scope"
    root.mkdir(parents=True, exist_ok=True)
    old_file = root / "fallback-old.tmp"
    old_file.write_text("fallback", encoding="utf-8")
    _touch_old(old_file, datetime.now() - timedelta(days=40))
    config = base / "fallback.yaml"
    config.write_text(
        f"""
system_temp:
  dirs:
    - "{root}"
  keep_days: 15
downloads:
  dirs: []
projects:
  roots:
    - "{base / "empty_code"}"
trash:
  command:
    - "/no/such/trash"
  retries: 0
scan:
  workers: 1
""".lstrip(),
        encoding="utf-8",
    )
    return config, old_file


def _build_unresolved_fixture(base: Path) -> tuple[Path, Path, Path, Path]:
    root = base / "unresolved_scope"
    root.mkdir(parents=True, exist_ok=True)
    old_file = root / "unresolved-old.tmp"
    old_file.write_text("unresolved", encoding="utf-8")
    _touch_old(old_file, datetime.now() - timedelta(days=40))

    blocked_outside = base / "outside_unresolved" / "blocked.tmp"
    blocked_outside.parent.mkdir(parents=True, exist_ok=True)
    blocked_outside.write_text("blocked", encoding="utf-8")

    block_file = base / ".codex" / "_trash_bin_" / "fallback-blocker"
    block_file.parent.mkdir(parents=True, exist_ok=True)
    block_file.write_text("not a directory", encoding="utf-8")
    fail_trash = base / "fail_trash.sh"
    fail_trash.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fail_trash.chmod(fail_trash.stat().st_mode | stat.S_IXUSR)

    config = base / "unresolved.yaml"
    config.write_text(
        f"""
system_temp:
  dirs:
    - "{root}"
  keep_days: 15
downloads:
  dirs: []
projects:
  roots:
    - "{base / "empty_code"}"
trash:
  command:
    - "{fail_trash}"
  retries: 0
failure_policy:
  external_trash_dir: "{block_file}"
scan:
  workers: 1
""".lstrip(),
        encoding="utf-8",
    )
    return config, old_file, blocked_outside, block_file


def _poison_project_watch_dir_cache(path: Path) -> None:
    cache_file = PROJECT_ROOT / "SWEEP" / "_cache" / "project_watch_dirs.json"
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    projects = payload.get("projects")
    if not isinstance(projects, list) or not projects or not isinstance(projects[0], dict):
        raise AssertionError("应至少存在一个可污染的项目缓存条目")
    watch_dirs = projects[0].get("watch_dirs")
    if not isinstance(watch_dirs, list):
        raise AssertionError("项目缓存条目应包含 watch_dirs")
    watch_dirs.append({"path": str(path), "kind": "temp"})
    cache_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _assert_move_candidates_revalidates_before_trash(
    config_path: Path,
    fixture: dict[str, Path],
) -> None:
    config = load_config(config_path, PROJECT_ROOT / "SWEEP")
    command = resolve_trash_command(config.trash.command)
    if command is None:
        raise AssertionError("fixture trash 命令应能解析")
    availability = TrashAvailability(command=command)

    old_time = datetime.now() - timedelta(days=40)
    race_file = fixture["system_dir"] / "became-new-before-move.tmp"
    race_file.write_text("old", encoding="utf-8")
    _touch_old(race_file, old_time)
    file_candidate = CleanupCandidate(
        path=race_file,
        scope_type=ScopeType.SYSTEM_TEMP,
        group=CandidateGroup.PARTIAL_ITEMS,
        kind=CandidateKind.FILE,
        keep_days=15,
        reason="fixture_pre_move_revalidate_file",
        watch_dir=fixture["system_dir"],
    )
    race_file.write_text("new", encoding="utf-8")

    file_summary = ExecutionSummary()
    _move_candidates([file_candidate], config, availability, file_summary)
    if not race_file.exists() or file_summary.moved:
        raise AssertionError("文件候选变新后不应被移动")
    _assert_skipped(file_summary, race_file)

    project_root = fixture["project"]
    watch_dir = fixture["trash_bin_root"]
    race_dir = watch_dir / "dir-with-new-child"
    race_dir.mkdir(parents=True, exist_ok=True)
    old_child = race_dir / "old.tmp"
    new_child = race_dir / "new.txt"
    old_child.write_text("old", encoding="utf-8")
    new_child.write_text("new", encoding="utf-8")
    _touch_old(old_child, old_time)
    _touch_old(race_dir, old_time)
    dir_candidate = CleanupCandidate(
        path=race_dir,
        scope_type=ScopeType.PROJECT,
        group=CandidateGroup.PARTIAL_ITEMS,
        kind=CandidateKind.DIRECTORY,
        keep_days=7,
        reason="fixture_pre_move_revalidate_directory",
        watch_dir=watch_dir,
        project_root=project_root,
    )

    dir_summary = ExecutionSummary()
    _move_candidates([dir_candidate], config, availability, dir_summary)
    if not race_dir.exists() or dir_summary.moved:
        raise AssertionError("目录包含新子项时不应被移动")
    _assert_skipped(dir_summary, race_dir)
    print("[PASS] 执行阶段重验会跳过失效候选")


def _run_sweep(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["UV_CACHE_DIR"] = str(PROJECT_ROOT / ".codex" / "uv-cache")
    env["TMPDIR"] = str(PROJECT_ROOT / ".codex" / "tmp")
    return subprocess.run(
        ["uv", "run", "--project", str(PROJECT_ROOT), "SWEEP", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )


def _load_json(stdout: str) -> dict[str, object]:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"stdout 应为 JSON，实际为:\n{stdout}") from exc


def _assert_ok(completed: subprocess.CompletedProcess[str], label: str) -> None:
    if completed.returncode != 0:
        raise AssertionError(
            f"{label} 失败，退出码 {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def _assert_candidate(summary: dict[str, object], path: Path, group: str) -> None:
    candidates = summary["candidates"]
    if not isinstance(candidates, list):
        raise AssertionError("摘要 candidates 必须是列表")
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("path") == str(path):
            if candidate.get("group") != group:
                raise AssertionError(f"{path} 应位于分组 {group}，实际为 {candidate}")
            return
    raise AssertionError(f"缺少预期候选: {path}")


def _assert_no_candidate(summary: dict[str, object], path: Path) -> None:
    candidates = summary["candidates"]
    if not isinstance(candidates, list):
        raise AssertionError("摘要 candidates 必须是列表")
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("path") == str(path):
            raise AssertionError(f"Unexpected candidate present: {path}")


def _assert_skipped(summary: ExecutionSummary, path: Path) -> None:
    for skipped in summary.skipped:
        if skipped.candidate.path == path and skipped.reason == "not_candidate":
            return
    raise AssertionError(f"缺少 {path} 的 skipped not_candidate 记录")


def _append_manual_blocked_unresolved(path: Path) -> None:
    _append_manifest_event(path, event="unresolved", code="root_owned")


def _append_manual_resolved(path: Path) -> None:
    _append_manifest_event(path, event="resolved", code="resolved")


def _append_manifest_event(path: Path, *, event: str, code: str) -> None:
    manifest = PROJECT_ROOT / "SWEEP" / "_cache" / "unresolved_failures.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "original_path": str(path),
        "failure_stage": "fixture",
        "failure_code": code,
        "message": "fixture marker",
        "scope_type": "system_temp",
        "group": "partial_items",
        "project_root": None,
    }
    with manifest.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        file.write("\n")


def _resolve_previous_fixture_manifest_entries() -> None:
    manifest = PROJECT_ROOT / "SWEEP" / "_cache" / "unresolved_failures.jsonl"
    if not manifest.is_file():
        return
    latest: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        path = payload.get("original_path")
        event = payload.get("event")
        if isinstance(path, str) and isinstance(event, str):
            latest[path] = event
    for raw_path, event in latest.items():
        if "SWEEP-FIXTURE-" in raw_path and event == "unresolved":
            _append_manual_resolved(Path(raw_path))


def _touch_old(path: Path, timestamp: datetime) -> None:
    epoch = timestamp.timestamp()
    os.utime(path, (epoch, epoch), follow_symlinks=False)


def _touch_tree_old(root: Path, timestamp: datetime) -> None:
    for child in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        _touch_old(child, timestamp)
    _touch_old(root, timestamp)


if __name__ == "__main__":
    sys.exit(main())
