# HELLO - AI CLI 连通性探测工具

## 工具简介

HELLO 是一个轻量级的 AI CLI 工具连通性探测器，用于检测 Claude Code 和 Codex CLI 的可用性、认证状态和基本响应能力。

**支持的服务：**
- **Claude Code** - Anthropic 官方 CLI 工具
- **Codex** - OpenAI Codex CLI

**主要功能：**
- 自动检测 CLI 工具是否安装
- 验证认证状态
- 发送测试请求并解析响应
- 支持并发探测多个服务
- 提供人类可读报告和机器可读 JSON 输出

## 安装与刷新

### 安装要求

- Python 3.12+
- uv
- 需要被探测的下游 CLI：`claude` 和/或 `codex`

### 全局命令刷新

`HELLO` 通过 `pyproject.toml` 的 `[project.scripts]` 注册为全局命令：

```toml
HELLO = "HELLO.cli:main"
```

修改代码、入口或依赖后，从仓库根目录刷新全局安装：

```bash
cd /Users/trouva/CODE/PYTHON/PyBits
uv tool install --force --reinstall --refresh .
```

安装完成后，`HELLO` 可以在任意目录直接运行。本地开发时可用：

```bash
uv run HELLO --help
```

## 基本用法

```bash
# 探测 Claude Code 和 Codex（默认，会发起真实 CLI 探测请求）
HELLO

# 只探测一个服务
HELLO claude
HELLO cc
HELLO codex
HELLO --service claude
HELLO --service codex

# 输出完整 JSON envelope，适合管道和日志
HELLO --raw

# 输出同一份缩进 JSON，主要用于人工调试
HELLO --pretty

# 只检查下游 CLI 调用，不额外执行认证状态命令
HELLO --skip-auth-check
```

只查看参数时使用 `HELLO --help`。不带参数的 `HELLO` 会同时调用 Claude Code 与 Codex 的实际探测命令。

## 命令行参数

### 输出模式（互斥）

| 参数 | 说明 | 默认 |
|------|------|------|
| `--compact` | 输出人类可读的中文紧凑报告 | 是 |
| `--raw` | 输出完整探测 JSON，使用 `indent=2` 格式化 | 否 |
| `--pretty` | 输出完整探测 JSON，当前与 `--raw` 使用同一 envelope 和缩进格式 | 否 |

### 探测参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--service` | 选择 | `both` | 指定服务，可重复使用；可选值为 `claude`、`codex`、`both`、`all` |
| `service_aliases` | 位置参数 | `both` | 可直接写 `HELLO claude`、`HELLO cc`、`HELLO claude_code`、`HELLO codex`、`HELLO both`、`HELLO all` |
| `--timeout` | 浮点数 | `120.0` | 单个认证检查或探测请求的超时时间（秒）；认证检查最多使用 30 秒 |
| `--prompt` | 字符串 | `"hi?"` | 发送给下游 CLI 的探测提示词 |
| `--tail-chars` | 整数 | `4000` | 进程 stderr 预览保留字符数 |

### 通用选项

| 参数 | 说明 |
|------|------|
| `--verbose, -v` | 将控制台日志级别提高到 INFO；日志输出到 stderr，并写入 `HELLO/logs/` |
| `--always-exit-zero` | 无论探测结果如何都返回退出码 0 |
| `--skip-auth-check` | 跳过 `claude auth status` 和 `codex login status` 认证状态检查 |

### Claude Code 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--claude-bin` | `claude` | Claude Code 可执行文件名或路径 |
| `--claude-settings` | `~/.claude/settings.json` | HELLO 读取并摘要展示的 Claude settings 路径；文件存在时也会传给 Claude Code |
| `--claude-setting-sources` | `user` | 传给 Claude Code 的 `--setting-sources` 值 |

Claude Code 探测命令会使用 `-p <prompt>`、`--output-format json`、`--no-session-persistence`、`--max-turns 1` 和空工具列表。

### Codex 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--codex-bin` | `codex` | Codex 可执行文件名或路径 |
| `--codex-home` | 未指定（子进程继承当前环境） | 指定后会设置 `CODEX_HOME`，并让 HELLO 默认检查 `<CODEX_HOME>/config.toml` |
| `--codex-config` | `~/.codex/config.toml` 或 `<CODEX_HOME>/config.toml` | HELLO 用于读取配置摘要的路径；它不会直接改变 Codex CLI 的实际加载路径 |
| `--codex-profile` | - | 传给 Codex CLI 的 `--profile` |
| `--codex-cd` | 临时目录 | Codex `exec` 的工作目录；未指定时 HELLO 使用临时目录 |

Codex 探测命令会使用 `codex exec --json --color never --ephemeral --skip-git-repo-check --sandbox read-only --output-last-message ... --cd ... <prompt>`。

如果需要 HELLO 展示的 Codex 配置与 Codex CLI 实际运行配置一致，优先显式传入 `--codex-home`。单独传 `--codex-config` 只会改变 HELLO 读取的配置摘要，不会把该路径转发给 Codex CLI。

## 输出格式

### Compact 模式（默认）

Compact 是人类可读的中文报告。成功时形如：

```text
总体连通性：全部成功
Claude Code：连通成功；使用的模型：sonnet；alwaysThinkingEnabled：true；耗时：1234 ms
Codex：连通成功；使用的模型：gpt-5.5；model_reasoning_effort：xhigh；model_providers：1 个；耗时：2345 ms
```

失败时形如：

```text
总体连通性：存在失败
Claude Code：连通失败；status=missing_cli；exit_code=未知；timed_out=未知；请运行 HELLO --raw 查看完整输出
Codex：连通失败；status=timeout；exit_code=未知；timed_out=true；请运行 HELLO --raw 查看完整输出
```

### Raw / Pretty JSON

`--raw` 和 `--pretty` 当前都会输出同一份完整 JSON envelope，格式化缩进为 2 个空格。日志和警告写入 stderr，JSON 写入 stdout，可用于管道：

```bash
HELLO --raw | jq '.ok'
```

Envelope 顶层字段如下，示例内容已删减：

```json
{
  "schema_version": "ai-cli-connectivity-probe/v1",
  "ok": false,
  "status": "failed",
  "started_at": "2026-06-04T05:45:28.168Z",
  "finished_at": "2026-06-04T05:45:28.170Z",
  "prompt": "hi?",
  "host": {
    "os": "macOS-26.5.1-arm64-arm-64bit",
    "python": "3.12.13",
    "executable": "/Users/trouva/CODE/PYTHON/PyBits/.venv/bin/python3",
    "cwd": "/Users/trouva/CODE/PYTHON/PyBits"
  },
  "services": [
    {
      "service": "codex",
      "ok": false,
      "status": "missing_cli"
    }
  ]
}
```

单个 `services` 条目的主要字段：

```json
{
  "service": "codex",
  "ok": false,
  "status": "missing_cli",
  "cli": {
    "binary": "codex",
    "path": null,
    "version": null
  },
  "config": {},
  "auth": {
    "checked": false,
    "ok": null,
    "reason": "cli_not_found"
  },
  "request": null,
  "response": null,
  "process": null,
  "warnings": [
    "Cannot find `codex` in PATH."
  ]
}
```

常见 `status` 值包括 `pass`、`failed`、`timeout`、`missing_cli` 和 `exception`。

### 退出码

| 退出码 | 说明 |
|--------|------|
| `0` | 请求探测的所有服务都成功，或使用了 `--always-exit-zero` |
| `1` | 一个或多个请求探测的服务失败 |
