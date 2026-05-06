# SKILLS

SKILLS 是一个本地/GitHub skills 仓库管理工具，支持将 skills 安装到 Claude Code 和 Codex 的 skills 目录。

## 功能特性

- 统一管理来自本地和 GitHub 的 skills
- 跨平台配置同步（支持 Windows/macOS/Linux）
- 支持 Claude Code 和 Codex 两种 agent
- 灵活的安装模式（复制或链接）
- GitHub 仓库代理支持
- 自动缓存管理和重建

## 项目结构

```
SKILLS/
├── _repos_cache/           # GitHub 仓库本地缓存（不同步）
├── logs/                   # 日志文件（不同步）
├── .repos.json             # 仓库元信息（同步）
├── .repos.local.json       # 本地路径映射（不同步）
├── src/                    # Python 源代码
└── README.md
```

## 配置文件说明

### `.repos.json`（可同步）

存储所有仓库的元信息，不包含机器特定路径。可以通过 git 或云盘在多台电脑间同步。

```json
{
  "repositories": [
    {
      "name": "vercel-labs/skills",
      "type": "github",
      "url": "https://github.com/vercel-labs/skills.git",
      "path": null,
      "local_path": null,
      "registered_at": "2026-05-06T18:15:27.193610"
    },
    {
      "name": "my_own_skills",
      "type": "local",
      "url": null,
      "path": null,
      "local_path": null,
      "registered_at": "2026-05-06T18:15:27.193610"
    }
  ]
}
```

### `.repos.local.json`（不同步）

存储机器特定的路径映射。每台电脑维护自己的路径配置，不应同步到版本控制。

```json
{
  "github_cache_paths": {
    "vercel-labs/skills": "/path/to/_repos_cache/vercel-labs_skills_20260506_181527"
  },
  "local_paths": {
    "my_own_skills": "/Users/username/CODE/SKILLS/my_own_skills"
  }
}
```

## 安装

本项目使用 `uv` 管理依赖：

```bash
uv sync
```

## 使用说明

### 注册仓库

**注册 GitHub 仓库**：

```bash
# 简写格式
python -m src register vercel-labs/skills

# 完整链接
python -m src register https://github.com/vercel-labs/skills

# 使用代理
python -m src register vercel-labs/skills --proxy http://127.0.0.1:7890

# 指定扫描深度
python -m src register vercel-labs/skills --depth 5
```

**注册本地仓库**：

```bash
# 自动使用目录名作为仓库名
python -m src register /path/to/local/skills --local

# 指定仓库名
python -m src register /path/to/local/skills --local --name my-skills
```

### 列出已注册的仓库

```bash
python -m src list
```

输出示例：
```
vercel-labs/skills    github    /path/to/_repos_cache/vercel-labs_skills_20260506_181527
my_own_skills         local     /Users/username/CODE/SKILLS/my_own_skills
```

### 移除仓库

```bash
python -m src remove vercel-labs/skills
```

注意：移除仓库不会删除已安装的 skills，需要手动删除。

### 扫描仓库

扫描所有已注册的仓库：

```bash
python -m src scan
```

扫描指定仓库：

```bash
python -m src scan vercel-labs/skills
```

指定扫描深度：

```bash
python -m src scan vercel-labs/skills --depth 5
```

### 安装 skills

**交互式安装**（推荐）：

```bash
python -m src install
```

交互式流程会引导你：
1. 选择仓库
2. 选择要安装的 skills（支持多选）
3. 选择目标 agent（claude / codex / all）
4. 选择安装范围（user / project）
5. 选择安装模式（copy / link）
6. 确认安装参数

**非交互式安装**：

```bash
# 安装单个 skill
python -m src install vercel-labs/skills python-engineering --scope user --mode copy

# 安装多个 skills
python -m src install vercel-labs/skills python-engineering code-review --scope user --mode copy

# 指定 agent
python -m src install vercel-labs/skills python-engineering --agent claude --scope user --mode copy
```

### 重建 GitHub 仓库缓存

当 `.repos.local.json` 丢失或 GitHub 仓库缓存被删除时，可以重建缓存：

```bash
python -m src build
```

可选参数：
- `--proxy <url>`：使用代理
- `--depth <int>`：扫描深度（默认 3）

### 清理未引用的缓存

清理 `_repos_cache/` 中不在 `.repos.json` 中的缓存目录：

```bash
python -m src clean
```

## 参数说明

### 通用参数

- `--proxy <url>`：指定代理（仅用于 GitHub 仓库克隆）
- `--depth <int>`：扫描深度（默认 3）

### 安装参数

- `--agent <claude|codex|all>`：指定目标 agent，默认 `all`
- `--scope <user|project>`：指定安装范围，**必须指定**
  - `user`：安装到用户级 skills 目录（`~/.claude/skills/` 或 `~/.codex/skills/`）
  - `project`：安装到项目级 skills 目录（`.claude/skills/` 或 `.codex/skills/`）
- `--mode <copy|link>`：指定安装模式，默认 `copy`
  - `copy`：复制 skill 目录
  - `link`：创建链接（Windows 使用 Junction，Mac/Linux 使用 symlink）

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

## 跨平台同步工作流

SKILLS 支持在多台电脑间同步配置：

### 场景 1：同步 GitHub 仓库

1. **机器 A**：注册 GitHub 仓库
   ```bash
   python -m src register vercel-labs/skills
   ```

2. **同步配置**：将 `.repos.json` 提交到 git 或通过云盘同步

3. **机器 B**：拉取配置后重建缓存
   ```bash
   python -m src build
   ```

4. **机器 B**：安装 skills
   ```bash
   python -m src install
   ```

### 场景 2：本地仓库

本地仓库的元信息会同步到 `.repos.json`，但路径映射存储在 `.repos.local.json`（不同步）。

1. **机器 A**：注册本地仓库
   ```bash
   python -m src register /path/to/my-skills --local --name my-skills
   ```

2. **同步配置**：`.repos.json` 包含本地仓库元信息，但 `path` 为 `null`

3. **机器 B**：看到本地仓库记录，但路径为空
   ```bash
   python -m src list
   # 输出：my-skills    local    None
   ```

4. **机器 B**：为同名仓库配置本地路径
   - 方法 1：重新注册（会更新 `.repos.local.json`）
     ```bash
     python -m src register /different/path/my-skills --local --name my-skills
     ```
   - 方法 2：手动编辑 `.repos.local.json`

### 需要同步的文件

- `.repos.json`：必须同步
- `.repos.local.json`：不应同步（加入 `.gitignore`）
- `_repos_cache/`：不应同步（加入 `.gitignore`）
- `logs/`：不应同步（加入 `.gitignore`）

## 日志

日志文件位于 `SKILLS/logs/` 目录，按日期分割（`skills_YYYY-MM-DD.log`），保留最近 30 天。

- 控制台输出：WARNING 及以上级别
- 文件输出：INFO 及以上级别

可通过环境变量 `SKILLS_LOG_LEVEL` 配置日志级别：

```bash
export SKILLS_LOG_LEVEL=DEBUG
```

## 开发

运行 ruff 检查和格式化：

```bash
uv run ruff check src/ --fix
uv run ruff format src/
```

## 许可证

MIT
