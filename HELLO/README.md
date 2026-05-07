# HELLO - AI CLI 连通性探测工具

## 工具简介

HELLO 是一个轻量级的 AI CLI 工具连通性探测器，用于检测 Claude Code 和 Codex CLI 的可用性、认证状态和基本响应能力。

**支持的服务：**
- **Claude Code** - Anthropic 官方 CLI 工具
- **Codex** - Amazon 内部 AI 编码助手 CLI

**主要功能：**
- 自动检测 CLI 工具是否安装
- 验证认证状态
- 发送测试请求并解析响应
- 支持并发探测多个服务
- 提供人类可读报告和机器可读 JSON 输出

## 安装与使用

### 安装要求

- Python 3.12+
- uv（Python 包管理器）

### 安装步骤

```bash
# 全局安装 HELLO 工具
cd d:/CODE/Python/PyBits
uv tool install --force .
```

安装完成后，`HELLO` 命令将全局可用，可以在任何目录直接使用。

### 基本用法

```bash
# 探测所有服务（默认，输出人类可读报告）
HELLO

# 探测特定服务
HELLO --service claude
HELLO --service codex

# 输出原始 JSON（适合管道和日志）
HELLO --raw

# 输出格式化 JSON（调试用）
HELLO --pretty
```

### 典型使用场景

**场景 1：快速检查 CLI 工具状态**
```bash
HELLO
```
输出人类可读的紧凑报告，显示每个服务的连通性状态。

**场景 2：集成到 CI/CD 管道**
```bash
HELLO --raw | jq '.ok'
```
输出 JSON 格式，便于脚本解析。

**场景 3：调试认证问题**
```bash
HELLO --verbose --pretty
```
显示详细日志和格式化的 JSON 输出。

## 命令行参数

### 输出模式（互斥）

| 参数 | 说明 | 默认 |
|------|------|------|
| `--raw` | 输出原始探测 JSON（适合管道和日志） | - |
| `--compact` | 输出人类可读紧凑报告 | ✓ |
| `--pretty` | 输出格式化的 JSON（调试用） | - |

### 探测参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--service` | 选择 | `both` | 指定探测的服务（claude/codex/both），可重复使用 |
| `--timeout` | 浮点数 | `120.0` | 超时时间（秒） |
| `--prompt` | 字符串 | `"hi?"` | 探测提示词 |
| `--tail-chars` | 整数 | `4000` | 响应预览字符数 |

### 其他选项

| 参数 | 说明 |
|------|------|
| `--verbose, -v` | 显示详细日志 |
| `--always-exit-zero` | 总是以退出码 0 退出 |
| `--skip-auth-check` | 跳过认证状态检查 |

### Claude Code 专用参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--claude-bin` | `claude` | Claude Code 可执行文件名或路径 |
| `--claude-settings` | `~/.claude/settings.json` | Claude settings.json 文件路径 |
| `--claude-setting-sources` | `user` | Claude 设置源（user/project/local） |

### Codex 专用参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--codex-bin` | `codex` | Codex 可执行文件名或路径 |
| `--codex-home` | - | CODEX_HOME 目录路径 |
| `--codex-config` | - | Codex config.toml 文件路径 |
| `--codex-profile` | - | Codex profile 名称 |
| `--codex-cd` | - | Codex exec 工作目录 |

## 输出格式

### Compact 模式（默认）

人类可读的紧凑报告，显示每个服务的关键信息：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Claude Code
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Status: pass
  CLI: claude (v1.2.3)
  Auth: ok
  Model: claude-sonnet-4-6
  Response: "Hello! How can I help you today?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Codex
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Status: pass
  CLI: codex (v2.0.1)
  Auth: ok
  Model: claude-opus-4-7
  Response: "Hi! I'm ready to help."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Overall: ✓ pass
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Raw 模式

紧凑的 JSON 输出，适合管道和日志：

```json
{"schema_version":"ai-cli-connectivity-probe/v1","ok":true,"status":"pass","started_at":"2026-05-08T10:30:00.123Z","finished_at":"2026-05-08T10:30:05.456Z","prompt":"hi?","host":{"os":"Windows-10-10.0.22631","python":"3.12.0","executable":"C:\\Python312\\python.exe","cwd":"D:\\CODE\\Python\\PyBits"},"services":[{"service":"claude_code","ok":true,"status":"pass",...},{"service":"codex","ok":true,"status":"pass",...}]}
```

**关键字段说明：**

- `schema_version` - JSON schema 版本标识
- `ok` - 总体状态（所有服务都成功时为 true）
- `status` - 总体状态字符串（pass/failed）
- `started_at` / `finished_at` - ISO8601 时间戳
- `prompt` - 使用的探测提示词
- `host` - 主机环境信息
- `services` - 各服务的探测结果数组

**单个服务结果结构：**

```json
{
  "service": "claude_code",
  "ok": true,
  "status": "pass",
  "started_at": "2026-05-08T10:30:00.123Z",
  "finished_at": "2026-05-08T10:30:02.456Z",
  "cli": {
    "binary": "claude",
    "path": "/usr/local/bin/claude",
    "version": "1.2.3"
  },
  "config": { ... },
  "auth": {
    "checked": true,
    "ok": true,
    "exit_code": 0,
    "duration_ms": 234
  },
  "request": { ... },
  "response": { ... },
  "process": {
    "command": "claude -p 'hi?' ...",
    "exit_code": 0,
    "timed_out": false,
    "duration_ms": 1234,
    "stdout_bytes": 567,
    "stderr_bytes": 0
  },
  "warnings": []
}
```

### Pretty 模式

格式化的 JSON 输出，便于阅读和调试：

```json
{
  "schema_version": "ai-cli-connectivity-probe/v1",
  "ok": true,
  "status": "pass",
  "started_at": "2026-05-08T10:30:00.123Z",
  "finished_at": "2026-05-08T10:30:05.456Z",
  "prompt": "hi?",
  "host": {
    "os": "Windows-10-10.0.22631",
    "python": "3.12.0",
    "executable": "C:\\Python312\\python.exe",
    "cwd": "D:\\CODE\\Python\\PyBits"
  },
  "services": [
    {
      "service": "claude_code",
      "ok": true,
      "status": "pass",
      ...
    }
  ]
}
```

### 退出码

| 退出码 | 说明 |
|--------|------|
| `0` | 所有探测的服务都成功 |
| `1` | 一个或多个服务失败 |

**注意：** 使用 `--always-exit-zero` 参数可以强制退出码为 0，适合某些 CI/CD 场景。
