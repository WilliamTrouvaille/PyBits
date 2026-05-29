"""仓库管理"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from git import Repo
from loguru import logger

from _shared.utils.trash import soft_delete

from .models import Repository, RepositoryType, Skill
from .skill import validate_skill
from .utils import (
    configure_git_proxy,
    ensure_dir,
    extract_skills_to_flat_structure,
    generate_timestamped_cache_dir_name,
    recursive_find_skills,
)

GITHUB_API_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class GitHubSkillSource:
    """Parsed GitHub URL pointing at one skill folder or a folder of skills."""

    owner: str
    repo: str
    branch: str
    path: str
    original_url: str

    @property
    def skill_hint(self) -> str:
        parts = [part for part in self.path.split("/") if part]
        if parts and parts[-1].lower() == "skill.md":
            parts = parts[:-1]
        return parts[-1] if parts else self.repo


def register_github_repo(
    url: str, proxy: str | None = None, repos_cache_dir: Path | None = None
) -> Repository:
    """
    注册 GitHub 仓库（新策略）
    1. 解析 URL（支持完整链接和简写）
    2. 克隆到缓存 staging 目录
    3. 递归扫描提取 skills 到带时间戳的缓存目录
    4. 软删除 staging 目录（包括 .git）
    5. 返回 Repository 对象

    Args:
        url: GitHub URL 或 owner/repo 简写
        proxy: 可选的 HTTP(S) 代理
        repos_cache_dir: 缓存目录路径
    """
    owner, repo = parse_github_url(url)
    repo_name = f"{owner}/{repo}"
    full_url = f"https://github.com/{owner}/{repo}.git"

    # 生成带时间戳的缓存目录名
    cache_dir = repos_cache_dir or Path(__file__).parent.parent / "_repos_cache"
    cache_dir_name = generate_timestamped_cache_dir_name(owner, repo)
    final_cache_path = cache_dir / cache_dir_name

    ensure_dir(cache_dir)
    staging_path = create_staging_dir(cache_dir, f"{owner}_{repo}_clone")
    try:
        clone_github_repo(full_url, staging_path, proxy)

        # 提取 skills 到缓存目录
        extracted_skills, conflicts = extract_skills_to_flat_structure(
            staging_path, final_cache_path
        )

        if conflicts:
            # 清理已创建的缓存目录
            if final_cache_path.exists():
                soft_delete(final_cache_path, "skills-register-conflict")

            conflict_details = "\n".join(
                f"  - '{name}': {', '.join(str(p) for p in paths)}"
                for name, paths in conflicts.items()
            )
            raise ValueError(f"仓库中存在重名 skills，无法注册:\n{conflict_details}")

        if not extracted_skills:
            logger.warning(f"仓库 {repo_name} 中未发现任何合法 skill")
    finally:
        if staging_path.exists():
            moved_staging = soft_delete(staging_path, "skills-github-staging")
            logger.debug(f"GitHub 注册 staging 已软删除: {staging_path} -> {moved_staging}")

    return Repository(
        name=repo_name,
        type=RepositoryType.GITHUB,
        url=full_url,
        path=None,
        local_path=final_cache_path,
        registered_at=datetime.now(),
    )


def register_github_skills(
    urls: list[str],
    name: str | None = None,
    proxy: str | None = None,
    repos_cache_dir: Path | None = None,
) -> Repository:
    """Register one or more GitHub skill URLs as a selected skills repository."""
    if not urls:
        raise ValueError("至少需要提供一个 GitHub skill URL")

    sources = [parse_github_skill_url(url) for url in urls]
    repo_name = github_skills_repository_name(sources, name)

    cache_dir = repos_cache_dir or Path(__file__).parent.parent / "_repos_cache"
    first_source = sources[0]
    cache_dir_name = generate_timestamped_cache_dir_name(first_source.owner, first_source.repo)
    final_cache_path = cache_dir / f"_{cache_dir_name}"

    ensure_dir(cache_dir)
    staging_path = create_staging_dir(cache_dir, f"{first_source.owner}_{first_source.repo}_selected")
    try:
        for index, source in enumerate(sources, 1):
            download_github_skill_source(
                source,
                staging_path / f"source_{index}",
                proxy=proxy,
            )

        extracted_skills, conflicts = extract_skills_to_flat_structure(
            staging_path, final_cache_path
        )
        if conflicts:
            if final_cache_path.exists():
                soft_delete(final_cache_path, "skills-selected-conflict")

            conflict_details = "\n".join(
                f"  - '{skill_name}': {', '.join(str(p) for p in paths)}"
                for skill_name, paths in conflicts.items()
            )
            raise ValueError(f"指定 URL 中存在重名 skills，无法注册:\n{conflict_details}")

        if not extracted_skills:
            if final_cache_path.exists():
                soft_delete(final_cache_path, "skills-selected-empty")
            raise ValueError("指定 URL 中未发现任何合法 skill")
    finally:
        if staging_path.exists():
            moved_staging = soft_delete(staging_path, "skills-selected-staging")
            logger.debug(f"精选 GitHub skills staging 已软删除: {staging_path} -> {moved_staging}")

    return Repository(
        name=repo_name,
        type=RepositoryType.GITHUB_SKILLS,
        url=None,
        path=None,
        local_path=final_cache_path,
        registered_at=datetime.now(),
        sources=urls,
    )


def github_skills_repository_name(
    sources: list[GitHubSkillSource],
    explicit_name: str | None = None,
) -> str:
    """Derive a stable display name for selected GitHub skills."""
    if explicit_name and explicit_name.strip():
        return explicit_name.strip()

    if len(sources) == 1:
        source = sources[0]
        return f"{source.owner}/{source.repo}:{source.skill_hint}"

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"selected-skills-{timestamp}"


def create_staging_dir(cache_dir: Path, label: str) -> Path:
    """Create a cache-local staging directory that callers can soft-delete."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_label = "".join(char if char.isalnum() or char in "-_" else "_" for char in label)
    staging_dir = cache_dir / f"_{safe_label}_{timestamp}_staging"
    ensure_dir(staging_dir)
    return staging_dir


def parse_github_skill_url(url: str) -> GitHubSkillSource:
    """Parse GitHub tree/blob/raw URLs that point at skill directories."""
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.strip("/").split("/") if part]

    if parsed.netloc == "github.com" and len(path_parts) >= 5:
        owner, repo, marker, branch, *rest = path_parts
        if marker == "tree":
            return GitHubSkillSource(owner, repo, branch, "/".join(rest), url)
        if marker == "blob":
            source_path = "/".join(rest)
            if source_path.lower().endswith("/skill.md"):
                source_path = source_path[: -len("/SKILL.md")]
            return GitHubSkillSource(owner, repo, branch, source_path, url)

    if parsed.netloc == "raw.githubusercontent.com" and len(path_parts) >= 5:
        owner, repo, branch, *rest = path_parts
        source_path = "/".join(rest)
        if source_path.lower().endswith("/skill.md"):
            source_path = source_path[: -len("/SKILL.md")]
        return GitHubSkillSource(owner, repo, branch, source_path, url)

    raise ValueError(f"无效的 GitHub skill URL: {url}")


def download_github_skill_source(
    source: GitHubSkillSource,
    target_dir: Path,
    proxy: str | None = None,
) -> None:
    """Download a GitHub directory through the Contents API."""
    ensure_dir(target_dir)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    api_path = quote(source.path.strip("/"), safe="/")
    api_url = f"https://api.github.com/repos/{source.owner}/{source.repo}/contents/{api_path}"
    params = {"ref": source.branch}
    logger.info(f"下载 GitHub skill URL: {source.original_url}")
    download_github_contents(api_url, target_dir, params=params, proxies=proxies)


def download_github_contents(
    api_url: str,
    target_dir: Path,
    *,
    params: dict[str, str] | None = None,
    proxies: dict[str, str] | None = None,
) -> None:
    """Recursively download files returned by the GitHub Contents API."""
    response = requests.get(
        api_url,
        params=params,
        proxies=proxies,
        timeout=GITHUB_API_TIMEOUT_SECONDS,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ValueError(f"GitHub Contents API 请求失败: HTTP {response.status_code} ({api_url})")

    payload = response.json()
    items = payload if isinstance(payload, list) else [payload]

    for item in items:
        item_type = item.get("type")
        item_name = item.get("name")
        if not isinstance(item_name, str):
            continue

        if item_type == "dir":
            child_url = item.get("url")
            if not isinstance(child_url, str):
                continue
            download_github_contents(
                child_url,
                target_dir / item_name,
                params=params,
                proxies=proxies,
            )
        elif item_type == "file":
            download_url = item.get("download_url")
            if not isinstance(download_url, str):
                continue
            download_github_file(download_url, target_dir / item_name, proxies)


def download_github_file(
    download_url: str,
    target_path: Path,
    proxies: dict[str, str] | None = None,
) -> None:
    """Download one raw GitHub file."""
    response = requests.get(download_url, proxies=proxies, timeout=GITHUB_API_TIMEOUT_SECONDS)
    if response.status_code < 200 or response.status_code >= 300:
        raise ValueError(f"GitHub 文件下载失败: HTTP {response.status_code} ({download_url})")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(response.content)


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

    repo_name = (name or "").strip() or path.name

    return Repository(
        name=repo_name,
        type=RepositoryType.LOCAL,
        url=None,
        path=path.resolve(),
        local_path=None,
        registered_at=datetime.now(),
    )


def clone_github_repo(
    url: str, target_dir: Path, proxy: str | None = None, repos_cache_dir: Path | None = None
) -> None:
    """
    克隆 GitHub 仓库
    - 使用 gitpython
    - 支持代理配置
    - 错误处理：网络错误、权限错误

    Args:
        url: GitHub 仓库 URL
        target_dir: 目标目录
        proxy: 可选的 HTTP(S) 代理
        repos_cache_dir: 缓存目录路径
    """
    cache_dir = repos_cache_dir or Path(__file__).parent.parent / "_repos_cache"
    ensure_dir(cache_dir)

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


def scan_repository(
    repo: Repository, max_depth: int = 3, excluded_dirs: set[str] | None = None
) -> list[Skill]:
    """
    扫描仓库中的所有合法 skills（递归扫描）
    - 递归遍历仓库目录
    - 调用 skill.validate_skill() 校验
    - 返回 Skill 列表

    Args:
        repo: 仓库对象
        max_depth: 最大扫描深度
        excluded_dirs: 排除的目录集合
    """
    # 确定扫描路径
    scan_path = (
        repo.local_path
        if repo.type in (RepositoryType.GITHUB, RepositoryType.GITHUB_SKILLS)
        else repo.path
    )

    if not scan_path or not scan_path.exists():
        logger.warning(f"仓库路径不存在: {scan_path}")
        return []

    # 递归查找所有包含 SKILL.md 的目录
    excluded = excluded_dirs or set()
    skill_dirs = recursive_find_skills(scan_path, max_depth, excluded)

    skills = []
    for skill_dir in skill_dirs:
        if validate_skill(skill_dir):
            skill = Skill.from_directory(skill_dir, repo.name)
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
