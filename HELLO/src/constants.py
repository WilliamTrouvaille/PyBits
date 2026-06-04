"""集中保存 HELLO 的默认探测参数和脱敏规则。"""

SCHEMA_VERSION = "ai-cli-connectivity-probe/v1"

DEFAULT_PROMPT = "hi?"

SECRET_KEY_HINTS = (
    "key",
    "token",
    "secret",
    "password",
    "credential",
    "authorization",
    "bearer",
    "cookie",
)

DEFAULT_TIMEOUT = 120.0

DEFAULT_TAIL_CHARS = 4000
