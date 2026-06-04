"""AIM 的 Claude/Codex 会话只读索引器。"""

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
    """
    描述一条已脱敏证据文件及其来源元数据。
    """

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
    """
    为 Claude 和 Codex 主目录生成脱敏证据索引。

    Args:
        claude_home: Claude Code 的主目录。
        codex_home: Codex 的主目录。
        out_dir: AIM 输出目录。
        since: 只索引此时间之后修改的文件；为 None 时不限制。
        limit: 最多写入的证据记录数。

    Returns:
        本次生成的证据记录列表。
    """
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
    """
    查找 agent 主目录下可能包含会话、日志或记忆信息的文件。

    Args:
        home: agent 主目录。

    Returns:
        按修改时间倒序排列的候选文件路径。
    """
    candidates: list[Path] = []
    for path in home.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() in {".jsonl", ".log"} or is_memory_file(path):
            candidates.append(path)

    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)


def is_memory_file(path: Path) -> bool:
    """
    判断文件名是否像记忆或项目指令文件。

    Args:
        path: 待判断的文件路径。

    Returns:
        文件名匹配记忆或指令文件特征时返回 True。
    """
    name = path.name
    return name in MEMORY_FILE_NAMES or "memory" in name.lower()


def build_evidence_record(agent: str, path: Path, evidence_dir: Path) -> Evidence | None:
    """
    创建单个脱敏证据文件及其索引记录。

    Args:
        agent: 证据来源 agent 名称。
        path: 原始候选文件路径。
        evidence_dir: 脱敏证据文件输出目录。

    Returns:
        成功生成的证据记录；原文件没有有效文本时返回 None。
    """
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
    """
    读取受长度限制的文本片段，避免一次性载入超大文件。

    Args:
        path: 待读取的候选文件路径。

    Returns:
        限长后的文本内容。
    """
    if path.suffix.lower() == ".jsonl":
        return read_jsonl_excerpt(path)

    size = path.stat().st_size
    if size > MAX_TEXT_FILE_BYTES:
        with path.open("rb") as file:
            data = file.read(MAX_TEXT_FILE_BYTES)
        return data.decode("utf-8", errors="replace")

    return path.read_text(encoding="utf-8", errors="replace")[:MAX_EVIDENCE_CHARS]


def read_jsonl_excerpt(path: Path) -> str:
    """
    逐行读取 JSONL 文件并保留可安全索引的摘要内容。

    Args:
        path: JSONL 文件路径。

    Returns:
        限长后的 JSONL 摘要文本。
    """

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
    """
    将单行 JSONL 压缩为稳定的摘要 JSON。

    Args:
        line: JSONL 原始行。

    Returns:
        可解析时返回压缩后的 JSON 字符串；不可解析时返回原行。
    """

    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return line

    compact = compact_json_value(value)
    return json.dumps(compact, ensure_ascii=False, sort_keys=True)


def compact_json_value(value: Any) -> Any:
    """
    保留 JSONL 记录的有用结构，同时限制嵌套内容规模。

    Args:
        value: 待压缩的 JSON 值。

    Returns:
        压缩后的 JSON 兼容值。
    """
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
    """
    对文本中的常见敏感信息做脱敏并限制长度。

    Args:
        text: 原始文本。

    Returns:
        脱敏后的限长文本。
    """

    redacted = text
    redacted = SECRET_PATTERNS[0].sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_PATTERNS[1].sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_PATTERNS[2].sub("[REDACTED_EMAIL]", redacted)
    return redacted[:MAX_EVIDENCE_CHARS]


def classify_file(path: Path) -> str:
    """
    根据文件后缀和名称推断证据类型。

    Args:
        path: 候选文件路径。

    Returns:
        AIM 使用的证据类型标识。
    """

    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return "session_jsonl"
    if suffix == ".log":
        return "log"
    if is_memory_file(path):
        return "memory_text"
    return "text"


def summarize_evidence(kind: str, text: str) -> str:
    """
    从证据文本中提取一行短摘要。

    Args:
        kind: 证据类型标识。
        text: 已脱敏的证据文本。

    Returns:
        面向报告展示的摘要文本。
    """

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line:
        return f"{kind} evidence with no non-empty preview"
    return first_line[:180]


def estimate_confidence(kind: str, text: str) -> str:
    """
    按证据类型和关键词粗略估计记忆候选置信度。

    Args:
        kind: 证据类型标识。
        text: 已脱敏的证据文本。

    Returns:
        置信度标识，取值保持机器可读英文。
    """

    if kind == "memory_text":
        return "high"
    if any(marker in text.lower() for marker in ("preference", "always", "never", "默认", "必须")):
        return "medium"
    return "low"


def recommend_action(kind: str) -> str:
    """
    为证据类型生成后续处理建议。

    Args:
        kind: 证据类型标识。

    Returns:
        后续动作标识，取值保持机器可读英文。
    """

    if kind == "memory_text":
        return "review_existing_memory"
    if kind == "session_jsonl":
        return "review_for_candidate_memory"
    return "keep_as_supporting_evidence"


def write_index(out_dir: Path, records: list[Evidence]) -> None:
    """
    写入 AIM 的 JSON 索引和 Markdown 候选报告。

    Args:
        out_dir: AIM 输出目录。
        records: 待写入的证据记录。
    """

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
    """
    渲染 AIM 候选记忆 Markdown 报告。

    Args:
        records: 待展示的证据记录。

    Returns:
        Markdown 报告文本。
    """

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
    """
    解析 `--since` 参数为 UTC 时间。

    Args:
        value: 用户传入的日期或 ISO 时间字符串。

    Returns:
        UTC 时间；未传入时返回 None。

    Raises:
        ValueError: 输入不是可解析的日期或时间。
    """

    if not value:
        return None

    normalized = value.strip()
    try:
        if len(normalized) == 10:
            parsed = datetime.fromisoformat(normalized)
        else:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"无效的 --since 值: {value}") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def modified_at(path: Path) -> datetime | None:
    """
    读取文件修改时间。

    Args:
        path: 文件路径。

    Returns:
        UTC 修改时间；无法读取时返回 None。
    """

    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def format_mtime(path: Path) -> str | None:
    """
    将文件修改时间格式化为 ISO 字符串。

    Args:
        path: 文件路径。

    Returns:
        ISO 时间字符串；无法读取时返回 None。
    """

    value = modified_at(path)
    return value.isoformat() if value else None
