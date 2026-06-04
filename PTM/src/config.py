"""PTM token 读取和日志脱敏辅助函数。"""

from __future__ import annotations

from pathlib import Path

from .constants import DOTENV_TOKEN_NAME
from .models import PTMError

DOTENV_RELATIVE_PATH = Path("PTM") / ".env"
PACKAGE_DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_PROJECT_DOTENV_PATH = Path.home() / "CODE" / "PYTHON" / "PyBits" / "PTM" / ".env"


def _clean_token(value: str | None) -> str:
    """
    去除 token 外层空白和常见引号。
    """

    if value is None:
        return ""
    return value.strip().strip('"').strip("'").strip()


def _load_dotenv_values(path: Path) -> dict[str, str]:
    """
    读取简单 `.env` 文件中的键值对。
    """

    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PTMError(
            f"无法读取 .env 文件: {path}",
            f"检查文件权限后重试。细节: {exc}",
        ) from exc

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = _clean_token(value)
    return values


def _candidate_dotenv_paths() -> list[Path]:
    """
    返回 PTM token 的候选 `.env` 查找路径。
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


def find_dotenv_path() -> Path:
    """
    查找本次加载 token 使用的 PTM `.env` 文件路径。
    """

    for path in _candidate_dotenv_paths():
        if path.is_file():
            return path
    return _candidate_dotenv_paths()[0]


def load_token() -> str:
    """
    从 PTM `.env` 文件读取 MinerU API token。

    Raises:
        PTMError: 未找到有效 token。
    """

    dotenv_path = find_dotenv_path()
    token = _clean_token(_load_dotenv_values(dotenv_path).get(DOTENV_TOKEN_NAME))
    if token:
        return token

    raise PTMError(
        "未提供 MinerU API token",
        f"在 {dotenv_path} 中添加 `{DOTENV_TOKEN_NAME}=your_api_token`。",
    )


def mask_token(token: str) -> str:
    """
    为日志输出遮蔽 token。
    """

    clean = _clean_token(token)
    if not clean:
        return "(empty)"
    if len(clean) <= 8:
        return "*" * len(clean)
    return f"{clean[:4]}...{clean[-4:]}"
