"""Read-only Claude/Codex session indexer for AIM."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MAX_EVIDENCE_CHARS = 2_000
MAX_TEXT_FILE_BYTES = 2_000_000

SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[^\s\"']+"),
    re.compile(r"(?i)((?:api[_-]?key|token|cookie|secret|password)\s*[:=]\s*)[^\s\"']+"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)

MEMORY_FILE_NAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "MEMORY.md",
    "memory.md",
    "memories.md",
}


@dataclass(frozen=True)
class Evidence:
    id: str
    agent: str
    kind: str
    source_path: str
    source_mtime: str | None
    evidence_path: str
    summary: str
    confidence: str
    recommended_action: str


def build_index(
    claude_home: Path,
    codex_home: Path,
    out_dir: Path,
    since: datetime | None,
    limit: int,
) -> list[Evidence]:
    """Build a redacted evidence index for Claude and Codex homes."""
    evidence_dir = out_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    records: list[Evidence] = []
    homes = (("claude", claude_home.expanduser()), ("codex", codex_home.expanduser()))
    for agent, home in homes:
        if not home.exists():
            continue
        for path in discover_source_files(home):
            if len(records) >= limit:
                break
            if since and modified_at(path) and modified_at(path) < since:
                continue
            record = build_evidence_record(agent, path, evidence_dir)
            if record:
                records.append(record)

    write_index(out_dir, records)
    return records


def discover_source_files(home: Path) -> list[Path]:
    """Find likely session, log, and memory files under an agent home."""
    candidates: list[Path] = []
    for path in home.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() in {".jsonl", ".log"} or is_memory_file(path):
            candidates.append(path)

    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)


def is_memory_file(path: Path) -> bool:
    """Return whether a file looks like a memory or instruction file."""
    name = path.name
    return name in MEMORY_FILE_NAMES or "memory" in name.lower()


def build_evidence_record(agent: str, path: Path, evidence_dir: Path) -> Evidence | None:
    """Create one redacted evidence file and matching index record."""
    text = read_source_excerpt(path)
    if not text.strip():
        return None

    redacted = redact_sensitive(text)
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    evidence_path = evidence_dir / f"{agent}_{path.stem}_{digest}.txt"
    evidence_path.write_text(redacted, encoding="utf-8")

    kind = classify_file(path)
    source_mtime = format_mtime(path)
    summary = summarize_evidence(kind, redacted)
    return Evidence(
        id=digest,
        agent=agent,
        kind=kind,
        source_path=str(path),
        source_mtime=source_mtime,
        evidence_path=str(evidence_path),
        summary=summary,
        confidence=estimate_confidence(kind, redacted),
        recommended_action=recommend_action(kind),
    )


def read_source_excerpt(path: Path) -> str:
    """Read a bounded text excerpt without loading arbitrarily large files."""
    if path.suffix.lower() == ".jsonl":
        return read_jsonl_excerpt(path)

    size = path.stat().st_size
    if size > MAX_TEXT_FILE_BYTES:
        with path.open("rb") as file:
            data = file.read(MAX_TEXT_FILE_BYTES)
        return data.decode("utf-8", errors="replace")

    return path.read_text(encoding="utf-8", errors="replace")[:MAX_EVIDENCE_CHARS]


def read_jsonl_excerpt(path: Path) -> str:
    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            lines.append(normalize_jsonl_line(stripped))
            if len("\n".join(lines)) >= MAX_EVIDENCE_CHARS:
                break
    return "\n".join(lines)[:MAX_EVIDENCE_CHARS]


def normalize_jsonl_line(line: str) -> str:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return line

    compact = compact_json_value(value)
    return json.dumps(compact, ensure_ascii=False, sort_keys=True)


def compact_json_value(value: Any) -> Any:
    """Keep useful shape from JSONL entries while bounding nested content."""
    if isinstance(value, dict):
        kept: dict[str, Any] = {}
        for key in ("timestamp", "created_at", "type", "role", "model", "cwd", "text", "content"):
            if key in value:
                kept[key] = compact_json_value(value[key])
        if kept:
            return kept
        return {key: compact_json_value(item) for key, item in list(value.items())[:6]}
    if isinstance(value, list):
        return [compact_json_value(item) for item in value[:4]]
    if isinstance(value, str):
        return value[:500]
    return value


def redact_sensitive(text: str) -> str:
    redacted = text
    redacted = SECRET_PATTERNS[0].sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_PATTERNS[1].sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_PATTERNS[2].sub("[REDACTED_EMAIL]", redacted)
    return redacted[:MAX_EVIDENCE_CHARS]


def classify_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return "session_jsonl"
    if suffix == ".log":
        return "log"
    if is_memory_file(path):
        return "memory_text"
    return "text"


def summarize_evidence(kind: str, text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line:
        return f"{kind} evidence with no non-empty preview"
    return first_line[:180]


def estimate_confidence(kind: str, text: str) -> str:
    if kind == "memory_text":
        return "high"
    if any(marker in text.lower() for marker in ("preference", "always", "never", "默认", "必须")):
        return "medium"
    return "low"


def recommend_action(kind: str) -> str:
    if kind == "memory_text":
        return "review_existing_memory"
    if kind == "session_jsonl":
        return "review_for_candidate_memory"
    return "keep_as_supporting_evidence"


def write_index(out_dir: Path, records: list[Evidence]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "aim-index/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "records": [asdict(record) for record in records],
    }
    (out_dir / "index.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "candidates.md").write_text(render_candidates(records), encoding="utf-8")


def render_candidates(records: list[Evidence]) -> str:
    lines = ["# AIM Candidate Memories", ""]
    if not records:
        lines.extend(
            [
                "未发现可索引的 Claude Code / Codex 会话、日志或 memory 文本。",
                "",
            ]
        )
        return "\n".join(lines)

    for record in records:
        lines.extend(
            [
                f"## {record.agent} / {record.kind} / {record.id}",
                "",
                f"- 来源: `{record.source_path}`",
                f"- 时间: `{record.source_mtime or 'unknown'}`",
                f"- 置信度: `{record.confidence}`",
                f"- 推荐动作: `{record.recommended_action}`",
                f"- 证据: `{record.evidence_path}`",
                f"- 摘要: {record.summary}",
                "",
            ]
        )
    return "\n".join(lines)


def parse_since(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.strip()
    try:
        if len(normalized) == 10:
            parsed = datetime.fromisoformat(normalized)
        else:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid --since value: {value}") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def modified_at(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def format_mtime(path: Path) -> str | None:
    value = modified_at(path)
    return value.isoformat() if value else None
