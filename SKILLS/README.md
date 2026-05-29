# SKILLS

SKILLS 是一个本地/GitHub skills 仓库管理工具，支持将 skills 安装到 Claude Code 和 Codex 的 skills 目录。

## 功能特性

- 统一管理来自本地和 GitHub 的 skills
- 跨平台配置同步（支持 Windows/macOS/Linux）
- 支持 Claude Code 和 Codex 两种 agent
- 灵活的安装模式（复制或链接）
- GitHub 仓库代理支持
- 自动缓存管理和重建
- 并发安全的持久化存储

## 项目结构

```
SKILLS/
├── _repos_cache/           # GitHub 仓库本地缓存（不同步）
├── logs/                   # 日志文件（不同步）
├── .repos.json             # 仓库元信息（同步）
├── .repos.local.json       # 本地路径映射（不同步）
├── setting.yaml            # 配置文件
├── src/                    # Python 源代码
└── README.md
```

## 安装

本项目使用 `uv` 管理依赖：

```bash
# 安装依赖
uv sync

# 或者安装为全局命令
uv tool install .
```

## 使用说明

### 注册仓库

**注册 GitHub 仓库**：

```bash
# 简写格式
SKILLS rg vercel-labs/skills

# 完整链接
SKILLS rg https://github.com/vercel-labs/skills

# 使用代理
SKILLS rg vercel-labs/skills --proxy http://127.0.0.1:7890

# 指定扫描深度
SKILLS rg vercel-labs/skills --depth 5
```

**注册本地仓库**：

```bash
# 自动使用目录名作为仓库名
SKILLS rg /path/to/local/skills --local

# 指定仓库名
SKILLS rg /path/to/local/skills --local --name my-skills
```

> **命令别名**：`register` 可简写为 `rg`

**注册指定 GitHub skill（自动识别）**：

`rg` 会自动判别 `source` 的类型，无需单独的子命令：

- `owner/repo` 或仓库主页链接 → 克隆**完整仓库**
- 带 `tree/` 或 `blob/` 子路径的链接、`raw.githubusercontent.com` 文件链接 → 只注册**该目录下的 skills**
- 本地存在的路径（或带 `--local`）→ 注册**本地仓库**

```bash
# 注册单个 skill 目录
SKILLS rg https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs

# 注册单个 SKILL.md 页面
SKILLS rg https://github.com/mattpocock/skills/blob/main/skills/engineering/grill-with-docs/SKILL.md
```

针对 skill 子路径的注册会通过 GitHub Contents API 只下载目标目录，缓存为 `github_skills`
类型的精选仓库（缓存目录以 `_` 前缀标记非完整仓库）。注册后可继续使用：

```bash
SKILLS scan "mattpocock/skills:grill-with-docs"
SKILLS install "mattpocock/skills:grill-with-docs" grill-with-docs --scope user --agent codex
SKILLS update "mattpocock/skills:grill-with-docs"
```

### 列出已注册的仓库

```bash
SKILLS ls
```

输出示例：
```
Type     Name                      Source
────────────────────────────────────────────────
github   vercel-labs/skills        https://github.com/...
local    my_own_skills             /path/to/local/skills
```

> **命令别名**：`ls` 可简写为 `list`

### 移除仓库

```bash
SKILLS rm vercel-labs/skills
```

> **命令别名**：`remove` 可简写为 `rm`

注意：移除仓库不会删除已安装的 skills，需要手动删除。

### 扫描仓库

扫描所有已注册的仓库：

```bash
SKILLS scan
```

扫描指定仓库：

```bash
SKILLS scan vercel-labs/skills
```

指定扫描深度：

```bash
SKILLS scan vercel-labs/skills --depth 5
```

### 安装 skills

**交互式安装**（推荐）：

```bash
SKILLS install
```

交互式流程会引导你：
1. 选择仓库
2. 选择要安装的 skills（支持多选）
3. 选择目标 agent（来自 `setting.yaml` 的 agents 键，默认含 claude / codex / all）
4. 选择安装范围（user / project）
5. 选择安装模式（copy / link）
6. 确认安装参数

**非交互式安装**：

```bash
# 安装单个 skill
SKILLS install vercel-labs/skills python-engineering --scope user --mode copy

# 安装多个 skills
SKILLS install vercel-labs/skills python-engineering code-review --scope user --mode copy

# 指定 agent
SKILLS install vercel-labs/skills python-engineering --agent claude --scope user --mode copy

# 指定项目目录（用于项目级安装）
SKILLS install vercel-labs/skills python-engineering --scope project --project-dir /path/to/project
```

### 重建 GitHub 仓库缓存

当 `.repos.local.json` 丢失或 GitHub 仓库缓存被删除时，可以重建缓存：

```bash
SKILLS build
```

可选参数：
- `--proxy <url>`：使用代理
- `--depth <int>`：扫描深度（默认 3）

### 清理未引用的缓存

软删除 `_repos_cache/` 中不在 `.repos.json` 中的缓存目录：

```bash
SKILLS clean
```

缓存清理、覆盖安装和注册失败后的缓存回收都会移动到 `.codex/_trash_bin_/`，不会直接硬删除。

### 常用 skills（favorite）

`favorite`（别名 `fav`）把常用 skill 收集到内置仓库 `_repos_cache/favorite/`，
该仓库会作为一条 `local` 记录出现在 `SKILLS ls` 与交互式安装的仓库列表中。

```bash
# 列出常用 skills（直接 SKILLS favorite 也会列出）
SKILLS favorite list

# 从已注册仓库复制 skill 到常用集合
SKILLS favorite add "mattpocock/skills:grill-with-docs" grill-with-docs

# 软删除某个常用 skill（移动到 .codex/_trash_bin_/）
SKILLS favorite remove grill-with-docs
```

`SKILLS clean` 不会清理 `favorite` 目录。

### 最近安装（recent）

每次安装成功后，被安装 skill 的名字会记录到 `.recent_installs.json`（去重，最新在前，最多 100 条）。

```bash
SKILLS recent
```

交互式安装（`SKILLS install`）的仓库选择列表顶部会出现 `[最近安装]` 快捷入口，
可直接从最近安装过的 skills 中挑选。

## 配置文件

配置文件位于 `SKILLS/setting.yaml`，可以自定义以下选项：

```yaml
# 日志配置
log_level: "INFO"
log_retention_days: 30

# 扫描配置
default_scan_depth: 3

# 扫描时排除的目录
excluded_dirs:
  - ".git"
  - ".github"
  - "tests"
  - "docs"
  # ... 其他排除目录

# 路径配置（设为 null 使用默认值）
repos_cache_dir: null  # 默认: SKILLS/_repos_cache
logs_dir: null         # 默认: SKILLS/logs

# Agent 安装目录配置
# 键名即 --agent 的取值；新增 agent（如 cursor）只需在此添加，无需改代码。
agents:
  claude:
    user: "~/.claude/skills"
    project: ".claude/skills"
  codex:
    user: "~/.agents/skills"
    project: ".agents/skills"

# 工作区列表，仅用于 SKILLS status 只读扫描各工作区的项目级 skills
workspaces:
  - "~/CODE"
```

如果配置文件不存在，SKILLS 会使用内置默认值。

### agents

`agents` 决定 `--agent` 的可选值与各 agent 的安装目录。键名（如 `claude`、`codex`）
即为 `--agent` 的取值，外加内置的 `all`（安装到所有已配置 agent）。要支持新的 agent
（如 Cursor、DeepSeek），只需在此新增一段配置，无需改动代码。

### workspaces

`workspaces` 是一组工作区根目录，**仅供 `SKILLS status` 只读扫描**，列出每个工作区下
各 agent 的项目级 skills（即 `agents.<agent>.project` 目录）。`status` 不会对工作区做任何写操作。

## 参数说明

### 通用参数

- `--proxy <url>`：指定代理（仅用于 GitHub 仓库克隆）
- `--depth <int>`：扫描深度（默认 3）

### 安装参数

- `--agent <name|all>`：指定目标 agent，默认 `all`。可选值来自 `setting.yaml` 的 `agents` 键
  （内置 `claude`、`codex`），外加 `all`（安装到所有已配置 agent）。安装目录由该 agent 配置决定。
- `--scope <user|project>`：指定安装范围，**必须指定**
  - `user`：安装到用户级 skills 目录（由 `agents.<agent>.user` 决定）
  - `project`：安装到项目级 skills 目录（由 `agents.<agent>.project` 决定）
- `--mode <copy|link>`：指定安装模式，默认 `copy`
  - `copy`：复制 skill 目录
  - `link`：创建链接（Windows 使用 Junction，Mac/Linux 使用 symlink）
- `--project-dir <path>`：指定项目目录（用于项目级安装），默认为当前工作目录

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
   SKILLS rg vercel-labs/skills
   ```

2. **同步配置**：将 `.repos.json` 提交到 git 或通过云盘同步

3. **机器 B**：拉取配置后重建缓存
   ```bash
   SKILLS build
   ```

4. **机器 B**：安装 skills
   ```bash
   SKILLS install
   ```

### 场景 2：本地仓库

本地仓库的元信息会同步到 `.repos.json`，但路径映射存储在 `.repos.local.json`（不同步）。

1. **机器 A**：注册本地仓库
   ```bash
   SKILLS rg /path/to/my-skills --local --name my-skills
   ```

2. **同步配置**：`.repos.json` 包含本地仓库元信息，但 `path` 为 `null`

3. **机器 B**：看到本地仓库记录，但路径为空
   ```bash
   SKILLS ls
   # 输出：my-skills    local    None
   ```

4. **机器 B**：为同名仓库配置本地路径
   - 方法 1：重新注册（会更新 `.repos.local.json`）
     ```bash
     SKILLS rg /different/path/my-skills --local --name my-skills
     ```
   - 方法 2：手动编辑 `.repos.local.json`

### 需要同步的文件

- `.repos.json`：必须同步
- `.repos.local.json`：不应同步（加入 `.gitignore`）
- `.recent_installs.json`：不应同步（本机最近安装记录）
- `_repos_cache/`：不应同步（加入 `.gitignore`）
- `logs/`：不应同步（加入 `.gitignore`）
- `setting.yaml`：可选同步（根据个人偏好）

## 日志

日志由共享的 `_shared/utils/logging` 统一管理，文件位于 `SKILLS/logs/` 目录，
按日期分割（`skills_YYYY-MM-DD.log`），过期日志会软删除到 `.codex/_trash_bin_/`。

- 控制台输出：WARNING 及以上级别
- 文件输出：DEBUG 及以上级别

日志保留天数可通过 `setting.yaml` 的 `log_retention_days` 配置。

## 开发

运行 ruff 检查和格式化：

```bash
uv run ruff check SKILLS/src --fix
uv run ruff format SKILLS/src
```

## 许可证

MIT
