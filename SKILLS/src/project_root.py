"""
SKILLS 项目根目录发现辅助函数。
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
from pathlib import Path
from urllib.parse import unquote, urlparse


def find_skills_project_root() -> Path:
    """
    查找 SKILLS 项目根目录
    优先从 CWD 向上查找 .repos.json 或 SKILLS/.repos.json
    如果找不到，回退到代码所在目录

    Returns:
        SKILLS 项目根目录路径
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

    # 回退到 SKILLS 数据目录（向后兼容）
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
        if (candidate / ".repos.json").exists():
            return candidate.resolve()

    return None
