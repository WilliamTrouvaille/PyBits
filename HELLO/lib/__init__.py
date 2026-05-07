"""HELLO 工具库"""

from .auth_checker import missing_cli_result, summarize_auth_check
from .config_parser import config_summary
from .constants import (
    DEFAULT_PROMPT,
    DEFAULT_TAIL_CHARS,
    DEFAULT_TIMEOUT,
    SCHEMA_VERSION,
)
from .logger import setup_logger
from .process import get_version, run_process
from .probe_builder import (
    assemble_service_result,
    build_claude_command,
    build_codex_command,
    build_process_result,
    expand_services,
)
from .report import build_report
from .response_normalizer import normalize_claude_response, normalize_codex_response
from .schema import AuthSummary, ProbeEnvelope, ProcessResult, ServiceResult
from .security import redact
from .spinner import Spinner, with_spinner
from .utils import (
    command_display,
    expand_path,
    parse_json_maybe,
    parse_jsonl,
    sha256_12,
    strip_ansi,
    tail_text,
    text_sha256_12,
    to_text,
    utc_now,
)

__all__ = [
    # auth_checker
    "missing_cli_result",
    "summarize_auth_check",
    # config_parser
    "config_summary",
    # constants
    "DEFAULT_PROMPT",
    "DEFAULT_TAIL_CHARS",
    "DEFAULT_TIMEOUT",
    "SCHEMA_VERSION",
    # logger
    "setup_logger",
    # process
    "get_version",
    "run_process",
    # probe_builder
    "assemble_service_result",
    "build_claude_command",
    "build_codex_command",
    "build_process_result",
    "expand_services",
    # report
    "build_report",
    # response_normalizer
    "normalize_claude_response",
    "normalize_codex_response",
    # schema
    "AuthSummary",
    "ProbeEnvelope",
    "ProcessResult",
    "ServiceResult",
    # security
    "redact",
    # spinner
    "Spinner",
    "with_spinner",
    # utils
    "command_display",
    "expand_path",
    "parse_json_maybe",
    "parse_jsonl",
    "sha256_12",
    "strip_ansi",
    "tail_text",
    "text_sha256_12",
    "to_text",
    "utc_now",
]
