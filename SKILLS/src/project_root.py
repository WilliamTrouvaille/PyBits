"""SKILLS 项目根目录发现辅助函数。"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
from pathlib import Path
from urllib.parse import unquote, urlparse


def find_skills_project_root() -> Path:
    """
    查找 SKILLS 项目根目录。

    优先从当前工作目录向上查找 `.repos.json` 或 `SKILLS/.repos.json`；
    找不到时，再从本地安装 metadata 反查原始 checkout 中的 `SKILLS/` 数据目录。

    Returns:
        SKILLS 项目根目录路径。
    """
    # 从 CWD 开始向上查找，兼容在 PyBits 根目录执行全局安装的 SKILLS。
    cwd = Path.cwd()
    for directory in [cwd, *cwd.parents]:
        if (directory / ".repos.json").exists():
            return directory
        nested_skills_dir = directory / "SKILLS"
        if (nested_skills_dir / ".repos.json").exists():
            return nested_skills_dir

    install_origin = find_project_root_from_install_origin()
    if install_origin:
        return install_origin

    # 最后的回退兼容直接从源码树运行且尚未创建 .repos.json 的场景。
    return Path(__file__).parents[1].resolve()


def find_project_root_from_install_origin() -> Path | None:
    """
    从本地安装 metadata 找回原始 checkout 中的 SKILLS 数据目录。

    Returns:
        找到的 SKILLS 数据目录；无法解析安装来源时返回 None。
    """
    try:
        distribution = importlib_metadata.distribution("pybits")
    except importlib_metadata.PackageNotFoundError:
        return None

    direct_url_text = distribution.read_text("direct_url.json")
    if not direct_url_text:
        return None

    try:
        direct_url_data = json.loads(direct_url_text)
    except json.JSONDecodeError:
        return None

    url = direct_url_data.get("url")
    if not isinstance(url, str):
        return None

    parsed_url = urlparse(url)
    if parsed_url.scheme != "file":
        return None

    origin_path = Path(unquote(parsed_url.path)).expanduser()
    candidates = [origin_path / "SKILLS", origin_path]
    for candidate in candidates:
        if _is_skills_project_root(candidate):
            return candidate.resolve()

    return None


def _is_skills_project_root(candidate: Path) -> bool:
    """
    判断候选路径是否像原始 checkout 中的 SKILLS 数据目录。

    Args:
        candidate: 待检查的路径。

    Returns:
        候选路径包含 SKILLS 源码入口和文档时返回 True。
    """
    return (
        candidate.is_dir()
        and (candidate / "cli.py").is_file()
        and (candidate / "src").is_dir()
        and (candidate / "README.md").is_file()
    )
