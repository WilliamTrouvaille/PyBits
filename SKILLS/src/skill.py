"""SKILL.md 元数据校验和解析。"""

from pathlib import Path

import yaml
from loguru import logger


def validate_skill(skill_dir: Path) -> bool:
    """
    校验 skill 目录是否包含合法的 `SKILL.md` 元数据。
    """
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        return False

    metadata = parse_skill_metadata(skill_md)
    if not metadata:
        logger.warning(
            f"Skill 不合法（frontmatter 格式错误或缺少必需字段），跳过: {skill_dir.name}"
        )
        print(f"警告: Skill '{skill_dir.name}' 不合法（frontmatter 格式错误或缺少必需字段），跳过")
        return False

    return True


def parse_skill_metadata(skill_md_path: Path) -> dict[str, str] | None:
    """
    解析 `SKILL.md` 的 YAML frontmatter。

    Args:
        skill_md_path: 待解析的 `SKILL.md` 路径。

    Returns:
        包含必需字段的元数据字典；解析失败或缺少字段时返回 None。
    """
    try:
        content = skill_md_path.read_text(encoding="utf-8")
        frontmatter_str = extract_frontmatter(content)
        if not frontmatter_str:
            return None

        metadata = yaml.safe_load(frontmatter_str)
        if not isinstance(metadata, dict):
            return None

        if "name" not in metadata or "description" not in metadata:
            return None

        return metadata
    except Exception as e:
        logger.warning(f"解析 SKILL.md 失败: {skill_md_path}, 错误: {e}")
        return None


def extract_frontmatter(content: str) -> str | None:
    """
    从 Markdown 内容中提取 YAML frontmatter。

    Args:
        content: Markdown 文件内容。

    Returns:
        YAML 字符串；不存在完整 frontmatter 时返回 None。
    """
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return None

    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])

    return None
