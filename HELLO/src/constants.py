"""常量定义"""

# Schema 版本
SCHEMA_VERSION = "ai-cli-connectivity-probe/v1"

# 默认提示词（从 "hello？" 改为 "hi?"）
DEFAULT_PROMPT = "hi?"

# 敏感键提示词
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

# 默认超时（秒）
DEFAULT_TIMEOUT = 120.0

# 默认尾部字符数
DEFAULT_TAIL_CHARS = 4000
