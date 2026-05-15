"""Skill 校验和解析"""

from pathlib import Path

import yaml
from loguru import logger


def validate_skill(skill_dir: Path) -> bool:
    """
    校验 skill 目录是否合法
    1. 检查 SKILL.md 是否存在
    2. 解析 frontmatter
    3. 验证 name 和 description 字段
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
    解析 SKILL.md 的 frontmatter
    - 使用 pyyaml 解析
    - 返回 frontmatter 字典，失败返回 None
    """
    try:
        content = skill_md_path.read_text(encoding="utf-8")
        frontmatter_str = extract_frontmatter(content)
        if not frontmatter_str:
            return None

        metadata = yaml.safe_load(frontmatter_str)
        if not isinstance(metadata, dict):
            return None

        # 验证必需字段
        if "name" not in metadata or "description" not in metadata:
            return None

        return metadata
    except Exception as e:
        logger.warning(f"解析 SKILL.md 失败: {skill_md_path}, 错误: {e}")
        return None


def extract_frontmatter(content: str) -> str | None:
    """
    从 markdown 内容中提取 frontmatter
    - 查找 --- 包裹的 YAML 块
    - 返回 YAML 字符串，失败返回 None
    """
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return None

    # 查找第二个 ---
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])

    return None
