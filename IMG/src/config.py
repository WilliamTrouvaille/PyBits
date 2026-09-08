"""IMG `.env` 配置读取和脱敏辅助函数。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse, urlunsplit

from .constants import DOTENV_DEFAULT_PROVIDER, DOTENV_PROVIDER_NAMES
from .models import IMGError, ProviderConfig

DOTENV_RELATIVE_PATH = Path("IMG") / ".env"
PACKAGE_DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_PROJECT_DOTENV_PATH = Path.home() / "CODE" / "PYTHON" / "PyBits" / "IMG" / ".env"


def clean_value(value: str | None) -> str:
    """
    去除 `.env` 值外层空白和常见引号。
    """

    if value is None:
        return ""
    return value.strip().strip('"').strip("'").strip()


def load_dotenv_values(path: Path) -> dict[str, str]:
    """
    读取简单 `.env` 文件中的键值对。

    Args:
        path: `.env` 文件路径。

    Returns:
        解析出的键值表；文件不存在时返回空字典。

    Raises:
        IMGError: 文件存在但无法读取。
    """

    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise IMGError(
            f"无法读取 .env 文件: {path}",
            f"检查文件权限后重试。细节: {exc}",
        ) from exc

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = clean_value(value)
    return values


def find_dotenv_path() -> Path:
    """
    查找本次加载配置使用的 IMG `.env` 文件路径。
    """

    for path in candidate_dotenv_paths():
        if path.is_file():
            return path
    return candidate_dotenv_paths()[0]


def candidate_dotenv_paths() -> list[Path]:
    """
    返回 IMG `.env` 的候选查找路径。
    """

    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        candidates.append(parent / DOTENV_RELATIVE_PATH)

    candidates.extend(
        [
            DEFAULT_PROJECT_DOTENV_PATH,
            PACKAGE_DOTENV_PATH,
        ]
    )

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def load_provider_config(provider_name: str | None = None) -> ProviderConfig:
    """
    按确定性规则从 `.env` 读取当前 provider。

    Args:
        provider_name: CLI 显式指定的 provider 名称。

    Returns:
        当前请求应使用的 provider 配置。

    Raises:
        IMGError: `.env` 缺失、provider 未声明或选中 provider 字段不完整。
    """

    dotenv_path = find_dotenv_path()
    values = load_dotenv_values(dotenv_path)
    provider_names = parse_provider_names(values.get(DOTENV_PROVIDER_NAMES))

    if not provider_names:
        raise IMGError(
            "未配置 IMG provider",
            f"在 {dotenv_path} 中添加 `{DOTENV_PROVIDER_NAMES}=main,backup`。",
        )

    selected_name = (
        clean_value(provider_name) or values.get(DOTENV_DEFAULT_PROVIDER) or provider_names[0]
    )
    selected_key = provider_key(selected_name)
    provider_lookup = {provider_key(name): name for name in provider_names}
    if selected_key not in provider_lookup:
        available = ", ".join(provider_names)
        raise IMGError(
            f"未找到 provider: {selected_name}",
            f"在 `{DOTENV_PROVIDER_NAMES}` 中选择一个已声明名称。当前可用: {available}。",
        )

    display_name = provider_lookup[selected_key]
    prefix = f"IMG_{selected_key}_"
    base_url = normalize_base_url(values.get(f"{prefix}BASE_URL"))
    api_key = clean_value(values.get(f"{prefix}API_KEY"))
    model = clean_value(values.get(f"{prefix}MODEL"))

    missing = [
        field
        for field, value in (
            ("BASE_URL", base_url),
            ("API_KEY", api_key),
            ("MODEL", model),
        )
        if not value
    ]
    if missing:
        missing_vars = ", ".join(f"{prefix}{field}" for field in missing)
        raise IMGError(
            f"provider `{display_name}` 配置不完整",
            f"在 {dotenv_path} 中补充: {missing_vars}。",
        )

    return ProviderConfig(
        name=display_name,
        base_url=base_url,
        api_key=api_key,
        model=model,
        dotenv_path=dotenv_path,
    )


def parse_provider_names(raw_value: str | None) -> list[str]:
    """
    解析逗号分隔的 provider 名称列表。
    """

    names: list[str] = []
    seen: set[str] = set()
    for item in clean_value(raw_value).split(","):
        name = item.strip()
        if not name:
            continue
        key = provider_key(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def provider_key(name: str) -> str:
    """
    将 provider 名称转换为 `.env` 变量片段。
    """

    key = re.sub(r"[^A-Za-z0-9]+", "_", clean_value(name)).strip("_").upper()
    if not key:
        raise IMGError(
            "provider 名称无效",
            "provider 名称至少需要包含一个字母或数字。",
        )
    return key


def normalize_base_url(raw_url: str | None) -> str:
    """
    将用户填写的 base URL 规范化为 OpenAI 兼容的 `/v1` 根地址。

    用户可以只填写 `https://example.com`，也可以填写完整的
    `https://example.com/v1`；本函数会避免重复追加 `/v1`。
    """

    value = clean_value(raw_url).rstrip("/")
    if not value:
        return ""

    if "://" not in value:
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise IMGError(
            f"BASE_URL 格式无效: {raw_url}",
            "使用类似 `https://example.com` 或 `https://example.com/v1` 的地址。",
        )

    path = parsed.path.rstrip("/")
    if path != "/v1" and not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def mask_token(token: str) -> str:
    """
    为日志输出遮蔽 API key。
    """

    clean = clean_value(token)
    if not clean:
        return "(empty)"
    if len(clean) <= 8:
        return "*" * len(clean)
    return f"{clean[:4]}...{clean[-4:]}"


def host_only(url: str) -> str:
    """
    从 base URL 中提取主机名，解析失败时返回原始字符串。
    """

    parsed = urlparse(url)
    return parsed.netloc or url
