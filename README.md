# PyBits

个人常用的 Python 小工具集合。各工具独立运行，统一使用 uv 管理依赖。

## 项目结构

```
PyBits/
├── HELLO/              # Claude Code 和 Codex CLI 连通性探测工具
├── SKILLS/             # Skills 仓库管理和安装工具
├── CLI/                # 命令行脚本（zsh/PowerShell）
├── pyproject.toml      # 统一依赖管理
└── README.md
```

## 环境要求

- Python >= 3.13
- uv（Python 包管理工具）

## 安装

克隆仓库后安装依赖：

```bash
cd PyBits
uv sync
```

## 工具说明

### HELLO

探测 Claude Code 和 Codex CLI 的连通性，发送测试请求并输出标准化的 JSON 结果。

**主要功能**：
- 探测 Claude Code 和 Codex CLI 是否可用
- 检查认证状态
- 发送测试 prompt 并解析响应
- 支持并发或串行探测
- 输出标准化的 JSON 或人类可读的报告

**使用示例**：

```bash
# 探测所有服务（默认）
HELLO

# 只探测 Claude Code
HELLO cc

# 只探测 Codex
HELLO codex

# 输出紧凑报告
HELLO --compact

# 输出原始 JSON
HELLO --raw

# 自定义 prompt 和超时
HELLO --prompt "你好" --timeout 60

# 跳过认证检查
HELLO --skip-auth-check

# 串行探测（默认并发）
HELLO --sequential
```

**输出格式**：
- 默认：人类可读的彩色报告
- `--compact`：紧凑的单行报告
- `--raw`：原始 JSON
- `--pretty`：格式化的 JSON
- `--jsonl`：每个服务一行 JSON

**配置选项**：
- `--claude-bin`：Claude Code 可执行文件路径（默认 `claude`）
- `--claude-settings`：Claude Code 配置文件路径（默认 `~/.claude/settings.json`）
- `--codex-bin`：Codex 可执行文件路径（默认 `codex`）
- `--codex-home`：Codex 主目录路径
- `--codex-profile`：Codex 配置文件名

详细文档：[HELLO/README.md](HELLO/README.md)（待补充）

---

### SKILLS

本地和 GitHub skills 仓库管理工具，支持跨平台配置同步。

**主要功能**：
- 注册和管理本地/GitHub skills 仓库
- 扫描仓库中的 skills
- 安装 skills 到 Claude Code 或 Codex
- 支持复制或链接模式
- 跨平台配置同步（Windows/macOS/Linux）
- GitHub 仓库缓存管理

**使用示例**：

```bash
# 注册 GitHub 仓库
SKILLS register vercel-labs/skills

# 注册本地仓库
SKILLS register /path/to/local/skills --local --name my-skills

# 列出已注册的仓库
SKILLS list

# 扫描仓库中的 skills
SKILLS scan

# 交互式安装 skills
SKILLS install

# 非交互式安装
SKILLS install vercel-labs/skills python-engineering --scope user --mode copy

# 重建 GitHub 仓库缓存
SKILLS build

# 清理未引用的缓存
SKILLS clean

# 移除仓库
SKILLS remove vercel-labs/skills
```

**配置文件**：
- `.repos.json`：仓库元信息（可同步）
- `.repos.local.json`：本地路径映射（不同步）

**跨平台同步**：
- 将 `.repos.json` 提交到 git 或通过云盘同步
- 每台电脑维护自己的 `.repos.local.json`
- 在新电脑上运行 `SKILLS build` 重建 GitHub 仓库缓存

详细文档：[SKILLS/README.md](SKILLS/README.md)

---

## CLI 脚本

`CLI/` 目录包含各工具的命令行包装脚本：

- `CLI/HELLO`：HELLO 工具的 zsh 包装脚本
- `CLI/SKILLS`：SKILLS 工具的 zsh 包装脚本

这些脚本可以添加到 `PATH` 中，方便全局调用：

```bash
# 添加到 ~/.zshrc 或 ~/.bashrc
export PATH="/Users/trouva/CODE/PYTHON/PyBits/CLI:$PATH"
```

## 依赖管理

所有工具共享统一的依赖配置（`pyproject.toml`），主要依赖：

- `loguru`：日志记录
- `questionary`：交互式命令行界面
- `gitpython`：Git 操作
- `pyyaml`：YAML 解析
- `rich`：终端输出美化
- `ruff`：代码检查和格式化

## 开发

运行代码检查和格式化：

```bash
# 检查代码
uv run ruff check . --fix

# 格式化代码
uv run ruff format .
```

## 许可证

MIT
