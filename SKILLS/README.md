# SKILLS

SKILLS 是一个本地/GitHub skills 仓库到指定 agent skills 目录的同步器。

## 功能特性

- 📦 **统一管理**：集中管理来自本地和 GitHub 的 skills
- 🔄 **多机器同步**：通过同步 `.repos.json` 文件，在不同机器上快速重建 skills 环境
- 🎯 **多 agent 支持**：同时支持 Claude Code 和 Codex
- 🔗 **灵活安装**：支持复制（copy）或链接（link）模式
- 🌐 **代理支持**：支持通过代理克隆 GitHub 仓库

## 项目结构

```
SKILLS/
├── _repos_cache/      # GitHub 仓库本地缓存（不同步）
├── logs/              # 日志文件（不同步）
├── .repos.json        # 持久化文件（同步）
├── src/               # Python 源代码
└── README.md
```

## 安装

本项目使用 `uv` 管理依赖。确保已安装所需依赖：

```bash
uv sync
```

## 使用说明

### 注册仓库

注册 GitHub 仓库（支持完整链接和简写）：

```bash
# 完整链接
python -m SKILLS.src register https://github.com/vercel-labs/skills

# 简写
python -m SKILLS.src register vercel-labs/skills

# 使用代理
python -m SKILLS.src register vercel-labs/skills --proxy http://127.0.0.1:7890
```

注册本地仓库：

```bash
python -m SKILLS.src register /path/to/local/skills
```

### 列出已注册的仓库

```bash
python -m SKILLS.src ls
```

### 移除仓库

```bash
python -m SKILLS.src remove vercel-labs/skills
```

**注意**：移除仓库不会删除已安装的 skills，需要手动删除。

### 扫描仓库

扫描所有已注册的仓库：

```bash
python -m SKILLS.src scan
```

扫描指定仓库：

```bash
python -m SKILLS.src scan vercel-labs/skills
```

### 安装 skills

**非交互式安装**（指定仓库和 skill 名称）：

```bash
# 安装单个 skill
python -m SKILLS.src install vercel-labs/skills python-engineering --scope user --mode copy

# 安装多个 skills
python -m SKILLS.src install vercel-labs/skills python-engineering code-review --scope user --mode copy

# 指定 agent
python -m SKILLS.src install vercel-labs/skills python-engineering --agent claude --scope user --mode copy
```

**交互式安装**（无参数）：

```bash
python -m SKILLS.src install
```

交互式流程会引导你：
1. 选择仓库
2. 选择要安装的 skills（支持多选）
3. 选择目标 agent（claude / codex / all）
4. 选择安装范围（user / project）
5. 选择安装模式（copy / link）
6. 确认安装参数

### 参数说明

- `--agent <claude|codex|all>`：指定目标 agent，默认 `all`
- `--scope <user|project>`：指定安装范围，**必须指定**
  - `user`：安装到用户级 skills 目录（`~/.claude/skills/` 或 `~/.codex/skills/`）
  - `project`：安装到项目级 skills 目录（`.claude/skills/` 或 `.codex/skills/`）
- `--mode <copy|link>`：指定安装模式，默认 `copy`
  - `copy`：复制 skill 目录
  - `link`：创建链接（Windows 使用 Junction，Mac/Linux 使用 symlink）
- `--proxy <url>`：指定代理（仅用于 GitHub 仓库克隆）

## Skill 校验规则

一个合法的 skill 必须满足：

1. 目录中存在 `SKILL.md` 文件
2. `SKILL.md` 包含合法的 YAML frontmatter（`---` 包裹）
3. frontmatter 中必须包含 `name` 和 `description` 字段

示例 `SKILL.md`：

```markdown
---
name: my-skill
description: "这是一个示例 skill"
---

# My Skill

Skill 的详细说明...
```

## 日志

日志文件位于 `SKILLS/logs/` 目录，按日期分割（`skills_YYYY-MM-DD.log`），保留最近 30 天。

- 控制台输出：WARNING 及以上级别
- 文件输出：INFO 及以上级别

可通过环境变量 `SKILLS_LOG_LEVEL` 配置日志级别：

```bash
export SKILLS_LOG_LEVEL=DEBUG
```

## 多机器同步

SKILLS 设计用于多机器同步：

1. 在机器 A 上注册仓库并安装 skills
2. 将 `.repos.json` 文件同步到机器 B（通过 git、云盘等）
3. 在机器 B 上运行 `SKILLS build`（未来功能）重建 GitHub 仓库缓存
4. 在机器 B 上安装 skills

**注意**：`_repos_cache/` 和 `logs/` 目录不需要同步，只同步 `.repos.json` 文件。

## 未来扩展

- `SKILLS build`：从 `.repos.json` 重建所有 GitHub 仓库的本地缓存
- `SKILLS update`：更新已注册的 GitHub 仓库（git pull）
- `SKILLS status`：显示当前状态（已注册仓库、已安装 skills）

## 开发

运行 ruff 检查和格式化：

```bash
uv run ruff check SKILLS/src/ --fix
uv run ruff format SKILLS/src/
```

## 许可证

MIT
