"""仓库管理"""

from datetime import datetime
from pathlib import Path

from git import Repo
from loguru import logger

from .config import REPOS_CACHE_DIR
from .models import Repository, RepositoryType, Skill
from .skill import validate_skill
from .utils import configure_git_proxy, ensure_dir


def register_github_repo(url: str, proxy: str | None = None) -> Repository:
    """
    注册 GitHub 仓库
    1. 解析 URL（支持完整链接和简写）
    2. 克隆到 _repos_cache/
    3. 返回 Repository 对象
    """
    owner, repo = parse_github_url(url)
    repo_name = f"{owner}/{repo}"
    full_url = f"https://github.com/{owner}/{repo}.git"

    # 确定本地缓存路径
    cache_dir_name = f"{owner}-{repo}"
    local_path = REPOS_CACHE_DIR / cache_dir_name

    # 克隆仓库
    clone_github_repo(full_url, local_path, proxy)

    return Repository(
        name=repo_name,
        type=RepositoryType.GITHUB,
        url=full_url,
        path=None,
        local_path=local_path,
        registered_at=datetime.now(),
    )


def register_local_repo(path: Path, name: str | None = None) -> Repository:
    """
    注册本地仓库
    1. 验证路径存在
    2. 生成或使用指定的 name
    3. 返回 Repository 对象
    """
    if not path.exists():
        raise FileNotFoundError(f"本地路径不存在: {path}")

    if not path.is_dir():
        raise NotADirectoryError(f"路径不是目录: {path}")

    repo_name = name if name else path.name

    return Repository(
        name=repo_name,
        type=RepositoryType.LOCAL,
        url=None,
        path=path.resolve(),
        local_path=None,
        registered_at=datetime.now(),
    )


def clone_github_repo(url: str, target_dir: Path, proxy: str | None = None) -> None:
    """
    克隆 GitHub 仓库
    - 使用 gitpython
    - 支持代理配置
    - 错误处理：网络错误、权限错误
    """
    ensure_dir(REPOS_CACHE_DIR)

    env = {}
    if proxy:
        env = configure_git_proxy(proxy)
        logger.info(f"使用代理: {proxy}")

    try:
        logger.info(f"克隆仓库: {url} -> {target_dir}")
        Repo.clone_from(url, target_dir, env=env if env else None)
        logger.info(f"克隆成功: {target_dir}")
    except Exception as e:
        logger.error(f"克隆失败: {e}")
        raise


def scan_repository(repo: Repository) -> list[Skill]:
    """
    扫描仓库中的所有合法 skills
    - 遍历仓库目录
    - 调用 skill.validate_skill() 校验
    - 返回 Skill 列表
    """
    # 确定扫描路径
    if repo.type == RepositoryType.GITHUB:
        scan_path = repo.local_path
    else:
        scan_path = repo.path

    if not scan_path or not scan_path.exists():
        logger.warning(f"仓库路径不存在: {scan_path}")
        return []

    skills = []
    for item in scan_path.iterdir():
        if not item.is_dir():
            continue

        # 跳过隐藏目录和特殊目录
        if item.name.startswith(".") or item.name.startswith("_"):
            continue

        if validate_skill(item):
            skill = Skill.from_directory(item, repo.name)
            if skill:
                skills.append(skill)
                logger.debug(f"发现 skill: {skill.name}")

    logger.info(f"扫描仓库 {repo.name}，发现 {len(skills)} 个合法 skills")
    return skills


def parse_github_url(url: str) -> tuple[str, str]:
    """
    解析 GitHub URL
    - 支持完整链接：https://github.com/vercel-labs/skills
    - 支持简写：vercel-labs/skills
    - 返回 (owner, repo)
    """
    # 简写格式
    if "/" in url and not url.startswith(("http://", "https://")):
        parts = url.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]

    # 完整 URL
    if url.startswith(("http://", "https://")):
        parts = url.rstrip("/").split("/")
        if len(parts) >= 2:
            owner = parts[-2]
            repo = parts[-1].replace(".git", "")
            return owner, repo

    raise ValueError(f"无效的 GitHub URL: {url}")
