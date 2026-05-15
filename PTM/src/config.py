"""Token loading and masking helpers."""

from __future__ import annotations

from pathlib import Path

from .constants import DOTENV_TOKEN_NAME
from .models import PTMError

DOTENV_RELATIVE_PATH = Path("PTM") / ".env"
PACKAGE_DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_PROJECT_DOTENV_PATH = Path.home() / "CODE" / "PYTHON" / "PyBits" / "PTM" / ".env"


def _clean_token(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().strip('"').strip("'").strip()


def _load_dotenv_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PTMError(
            f"Cannot read .env file: {path}",
            f"Check file permissions and try again. Details: {exc}",
        ) from exc

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = _clean_token(value)
    return values


def _candidate_dotenv_paths() -> list[Path]:
    """Return .env lookup paths using only filesystem locations."""

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
    """Find the PTM .env file used for token loading."""

    for path in _candidate_dotenv_paths():
        if path.is_file():
            return path
    return _candidate_dotenv_paths()[0]


def load_token() -> str:
    """Load MinerU token from PTM/.env."""

    dotenv_path = find_dotenv_path()
    token = _clean_token(_load_dotenv_values(dotenv_path).get(DOTENV_TOKEN_NAME))
    if token:
        return token

    raise PTMError(
        "No API token provided",
        f"Add `{DOTENV_TOKEN_NAME}=your_api_token` to {dotenv_path}.",
    )


def mask_token(token: str) -> str:
    """Mask a token for logs."""

    clean = _clean_token(token)
    if not clean:
        return "(empty)"
    if len(clean) <= 8:
        return "*" * len(clean)
    return f"{clean[:4]}...{clean[-4:]}"
