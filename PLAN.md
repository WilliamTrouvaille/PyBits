# SKILLS 功能扩展和 Bug 修复计划

## 背景

SKILLS 是一个本地/GitHub skills 仓库到指定 agent skills 目录的同步器。本次开发旨在：

1. 修复现有 bug（扫描、注册、安装等）
2. 实现 README 中"未来扩展"的功能（build、update、status）
3. 改进用户体验（日志、交互式设计、进度提示）
4. 重构仓库管理策略（提取 skills、时间戳、缓存管理）

## 核心改动

### 1. 仓库管理策略重构

**当前问题**：

- 克隆完整 git 仓库到 `_repos_cache/`，占用空间大
- 无法扫描非平铺结构的 skills（如 `scientific-skills/skill-a/`）
- 重复注册同一仓库会报错（缓存冲突）

**新策略**：

- 注册时克隆仓库 → 递归扫描提取 skills → 平铺到缓存目录 → 删除原始结构（包括 .git）
- 缓存目录命名：`{owner}_{repo}_{YYYYMMDD}_{HHMMSS}`（例如 `K-Dense-AI_scientific-agent-skills_20260505_143022`）
- `.repos.json` 中每个仓库只保留一条记录（最新的），旧缓存目录保留但不引用
- 如果原仓库根目录有 `README.md`，复制到缓存目录

**缓存目录结构**：

```
_repos_cache/
  K-Dense-AI_scientific-agent-skills_20260505_143022/
    README.md  # 如果原仓库有
    skill-a/
      SKILL.md
      ...
    skill-b/
      SKILL.md
      ...
```

### 2. 递归扫描 skills

**当前问题**：

- `scan_repository()` 只扫描根目录的直接子目录
- 无法发现 `scientific-skills/skill-a/` 这种结构

**改进方案**：

- 递归扫描，查找所有包含 `SKILL.md` 的目录
- 默认扫描深度：3 层
- 支持命令行参数：`SKILLS scan --depth 5`
- 排除常见非 skills 目录：`.git`, `.github`, `.gitlab`, `docs`, `doc`, `documentation`, `tests`, `test`, `__tests__`, `examples`, `example`, `demos`, `demo`, `.vscode`, `.idea`, `.vs`, `scripts`, `tools`, `utils`

**skill 名称冲突处理**：

- 如果仓库中有两个不同路径的 skill 但名称相同（从 `SKILL.md` frontmatter 读取），拒绝注册并提示用户

**skill 名称合法性**：

- 正常情况：skill 已在文件夹中，直接使用文件夹名
- 特殊情况：`SKILL.md` 直接在根目录（无父文件夹），使用 frontmatter 中的 `name` 创建文件夹，自动清理非法字符（替换为 `_`），记录警告

### 3. 日志改造：以用户操作为核心

**当前问题**：

- 日志缺少用户行为记录（用户选择了什么、用户取消操作等）

**改进方案**：

- 日志分为两类：**用户操作** 和 **程序行为**
- 用户操作日志格式：`[用户操作] 具体操作内容`

**记录点**：

- `register`：用户注册了哪个仓库、来源类型、是否覆盖
- `remove`：用户移除了哪个仓库
- `scan`：用户扫描了哪个仓库、结果数量
- `install`：用户选择了哪些 skills、agent、scope、mode；用户主动取消（ESC/Ctrl+C）；安装成功/失败
- `update`：用户更新了哪些仓库
- `build`：用户重建了哪些仓库
- `clean`：用户清理了哪些缓存目录

**示例**：

```
2026-05-05 14:30:22 | INFO  | [用户操作] 注册仓库: K-Dense-AI/scientific-agent-skills (github)
2026-05-05 14:30:22 | INFO  | [用户操作] 选择安装 skills: python-engineering, code-review (agent=claude, scope=user, mode=copy)
2026-05-05 14:30:25 | INFO  | [用户操作] 用户主动取消安装
```

## 功能实现

### 4. `SKILLS register` 改进

**改进点**：

1. **进度提示**：克隆时显示"正在克隆仓库 xxx ..."
2. **自动扫描**：注册成功后自动扫描并显示发现的 skills（最多显示前 5 个，超出提示使用 `SKILLS scan` 查看完整列表）
3. **重复注册处理**：如果仓库已存在，询问用户"仓库已存在，是否覆盖？"，确认后创建新的时间戳目录并更新 `.repos.json`
4. **空仓库处理**：如果未发现任何合法 skill，提示"未发现任何合法 skill，是否继续注册？"，用户确认后再注册
5. **网络错误提示**：克隆失败时提示用户重试并建议使用 `--proxy` 参数

**输出示例**：

```
$ SKILLS register K-Dense-AI/scientific-agent-skills

正在克隆仓库 https://github.com/K-Dense-AI/scientific-agent-skills.git ...
克隆成功！

正在扫描仓库中的 skills（深度: 3）...
发现 15 个 skill（显示前 5 个）:
  skill-a    描述 A
  skill-b    描述 B
  skill-c    描述 C
  skill-d    描述 D
  skill-e    描述 E
  ...还有 10 个 skill，使用 SKILLS scan 查看完整列表

已注册仓库: K-Dense-AI/scientific-agent-skills (github)
缓存路径: D:\CODE\Python\PyBits\SKILLS\_repos_cache\K-Dense-AI_scientific-agent-skills_20260505_143022
```

### 5. `SKILLS scan` 改进

**改进点**：

1. **递归扫描**：使用新的递归扫描逻辑（深度 3，可通过 `--depth` 参数配置）
2. **交互式设计**：无参数时进入交互式，选择要扫描的仓库（时间排序，最新的在前）

**交互式流程**：

```
$ SKILLS scan
? 选择要扫描的仓库: (使用方向键选择)
  ❯ K-Dense-AI/scientific-agent-skills (github, 2026-05-05 14:30:22)
    vercel-labs/skills (github, 2026-05-04 10:15:30)
    (local) (local, 2026-05-03 09:00:00)
    [扫描所有仓库]

# 选择后显示扫描结果
K-Dense-AI/scientific-agent-skills: 15 个 skill
  skill-a    这是 skill a 的描述
  skill-b    这是 skill b 的描述
  ...
```

### 6. `SKILLS install` 改进

**改进点**：

1. **description 截断**：交互式选择 skills 时，description 截断到 100 字符，超出部分用 `...` 表示
2. **中文提示**：将 `questionary.checkbox` 的英文提示改为中文

**代码示例**：

```python
questionary.checkbox(
    "选择要安装的 skills:",
    choices=skill_labels,
    instruction="(方向键移动，空格选择，a 全选，i 反选)"
).ask()
```

### 7. `SKILLS build` 命令（核心功能）

**功能**：从 `.repos.json` 重建所有 GitHub 仓库的本地缓存，用于多机器同步场景。

**流程**：

```
$ SKILLS build

读取 .repos.json，发现 2 个仓库:
  1. K-Dense-AI/scientific-agent-skills (github) - 缓存不存在
  2. (local) (local) - 本地路径不存在，跳过

? 是否重建缺失的 GitHub 仓库缓存？(y/N)

正在克隆 K-Dense-AI/scientific-agent-skills ...
克隆成功！
正在扫描 skills（深度: 3）...
发现 15 个 skill（显示前 5 个）:
  skill-a    描述 A
  ...

重建完成！

检查缓存目录...
_repos_cache/ 中有 3 个目录，.repos.json 中有 2 个仓库。
提示: 使用 SKILLS clean 清理未使用的缓存目录。
```

**处理逻辑**：

- 遍历 `.repos.json` 中的所有仓库
- GitHub 仓库：直接克隆最新版本，提取 skills，更新 `.repos.json` 中的 `local_path`
- 本地仓库：检查路径是否存在，不存在则警告并跳过
- 不扫描"已存在缓存"，直接拉取最新仓库
- 执行完后比对 `_repos_cache/` 文件夹数量与 `.repos.json` 中仓库数量，不相等时提醒用户使用 `SKILLS clean`

### 8. `SKILLS update` 命令

**功能**：更新已注册的 GitHub 仓库（重新克隆，提取 skills，创建新的时间戳目录）。

**支持模式**：

1. **指定仓库**：`SKILLS update <repo-name>`
2. **交互式**：`SKILLS update`（无参数）

**交互式流程**：

```
$ SKILLS update
? 选择要更新的仓库: (方向键移动，空格选择，a 全选，i 反选)
  ❯ ◯ K-Dense-AI/scientific-agent-skills (github, 2026-05-05 14:30:22)
    ◯ vercel-labs/skills (github, 2026-05-04 10:15:30)

# 选择后确认
? 是否更新选中的 2 个仓库？(y/N)

正在更新 K-Dense-AI/scientific-agent-skills ...
克隆成功！
发现 16 个 skill（显示前 5 个）:
  skill-a    描述 A
  ...
以下 skills 可能有新版本: skill-a, skill-b, skill-c, skill-d, skill-e
...还有 11 个 skill，使用 SKILLS scan 查看完整列表

正在更新 vercel-labs/skills ...
...

更新完成！
```

**处理逻辑**：

- 重新克隆仓库，提取 skills，创建新的时间戳目录
- 更新 `.repos.json` 中的 `local_path` 和 `registered_at`
- 更新后提示"以下 skills 可能有新版本"（最多显示 5 个，超出提示使用 `SKILLS scan` 查看完整列表）
- 不自动重新安装 skills，用户需要手动重新安装

### 9. `SKILLS clean` 命令

**功能**：清理 `_repos_cache/` 中未在 `.repos.json` 中引用的缓存目录。

**流程**：

```
$ SKILLS clean

扫描 _repos_cache/ 目录...

发现以下缓存目录不在 .repos.json 中：
  1. K-Dense-AI_scientific-agent-skills_20260504_120000
  2. vercel-labs_skills_20260503_090000

总计: 2 个目录

? 是否删除这些目录？(y/N)

正在删除 K-Dense-AI_scientific-agent-skills_20260504_120000 ...
正在删除 vercel-labs_skills_20260503_090000 ...

清理完成！
```

**处理逻辑**：

- 遍历 `_repos_cache/` 中的所有目录
- 检查目录名是否匹配 `.repos.json` 中任何 `local_path` 的目录名
- 不匹配的目录列出，询问用户是否删除
- 确认后使用 `shutil.rmtree()` 永久删除（不软删除）

### 10. `SKILLS status` 命令

**功能**：显示已注册仓库和已安装 skills。

**流程**：

```
$ SKILLS status

已注册仓库: 2 个
  K-Dense-AI/scientific-agent-skills (github, 2026-05-05 14:30:22)
  (local) (local, 2026-05-04 23:58:55)

已安装 skills:
  用户级 (claude):
    python-engineering
    code-review

  用户级 (codex):
    无

  项目级 (claude):
    custom-skill

  项目级 (codex):
    无
```

**处理逻辑**：

- 显示 `.repos.json` 中的所有仓库
- 实时扫描 `~/.claude/skills/`、`~/.codex/skills/`、`.claude/skills/`、`.codex/skills/` 目录
- 只显示 skill 名称，不显示来源（因为不记录已安装 skills）

## 关键文件

需要修改的文件：

- `SKILLS/src/repository.py`：递归扫描、提取 skills、排除目录
- `SKILLS/src/__main__.py`：新增 build、update、clean、status 命令；改进 register、scan、install 的交互式设计
- `SKILLS/src/models.py`：可能需要调整 Repository 模型
- `SKILLS/src/persistence.py`：可能需要调整持久化逻辑
- `SKILLS/src/utils.py`：新增工具函数（递归扫描、提取 skills、清理非法字符等）
- `SKILLS/src/config.py`：新增配置常量（排除目录列表、默认扫描深度等）

## 验证计划

1. **仓库管理**：
   - 注册 GitHub 仓库（平铺结构 + 嵌套结构）
   - 重复注册同一仓库（测试覆盖逻辑）
   - 注册空仓库（测试提示逻辑）
   - 注册包含重名 skills 的仓库（测试冲突检测）

2. **扫描功能**：
   - 扫描嵌套结构仓库（深度 1、2、3、5）
   - 交互式扫描（选择单个仓库、扫描所有）
   - 验证排除目录逻辑

3. **安装功能**：
   - 交互式安装（验证 description 截断、中文提示）
   - 非交互式安装

4. **build 命令**：
   - 在新机器上从 `.repos.json` 重建缓存
   - 验证本地仓库的警告提示
   - 验证缓存数量比对提示

5. **update 命令**：
   - 更新单个仓库
   - 交互式更新多个仓库
   - 验证"可能有新版本"提示

6. **clean 命令**：
   - 清理未引用的缓存目录
   - 验证删除确认流程

7. **status 命令**：
   - 显示已注册仓库和已安装 skills
   - 验证多 agent、多 scope 的显示

8. **日志验证**：
   - 检查日志文件中是否正确记录用户操作
   - 验证 `[用户操作]` 标记

## 实现优先级

### P0（核心功能，必须实现）

1. 仓库管理策略重构（register 改进）
2. 递归扫描 skills
3. `SKILLS build` 命令
4. `SKILLS update` 命令

### P1（重要功能）

5. `SKILLS clean` 命令
6. `SKILLS status` 命令
7. 日志改造

### P2（体验优化）

8. `SKILLS scan` 交互式设计
9. `SKILLS install` 改进（description 截断、中文提示）

## 风险和注意事项

1. **向后兼容性**：新的仓库管理策略会导致旧的缓存目录结构失效。需要在文档中说明，建议用户重新注册仓库。
2. **skill 名称冲突**：严格检测可能导致某些仓库无法注册。需要在错误提示中明确指出冲突的 skill 名称和路径。
3. **网络稳定性**：`build` 和 `update` 命令可能需要克隆多个仓库，网络不稳定时可能失败。建议在文档中说明可以使用 `--proxy` 参数。
4. **跨平台兼容性**：文件路径、时间戳格式需要确保在 Windows、Mac、Linux 上都能正常工作。
5. **日志文件大小**：随着使用增加，日志文件可能变大。当前已有日志轮转机制（保留 30 天），应该足够。
