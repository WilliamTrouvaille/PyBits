# Ruff 工作流

> 本文件范围：ruff 迭代修复工作流（安全→不安全→手动、diff 审查、noqa 纪律）。
> 不在本文件范围：ruff 规则详解（用 `ruff rule <code>`）、pre-commit/CI 集成、其他 linter 配置。

## 核心流程：安全→不安全→手动

按以下三轮递进修复，每轮结束后 `ruff format` 再 `ruff check`：

1. **安全修复**：`ruff check --fix`
   - 仅应用 ruff 标记为安全的自动修复。
   - 审查 diff，确认语义正确后再继续。

2. **不安全修复**：`ruff check --fix --unsafe-fixes`
   - 在安全修复基础上应用不安全修复。
   - 审查 diff——不安全修复可能改变行为，逐条理解规则意图。

3. **手动修复**：逐条审查剩余违规
   - 对每条违规：要么修复代码，要么标注 `# noqa`（见下方纪律）。
   - 修复后 `ruff format` + `ruff check` 确认。

## diff 审查纪律

- 修复前必须预览：`ruff check --diff` / `ruff format --diff`。
- 确认变更范围合理后再应用。
- 不盲信自动修复：理解每条规则意图，尤其是 `--unsafe-fixes`。

## noqa 纪律

仅当同时满足以下条件时才使用 `# noqa: <RULE>`：

- 规则与必要行为冲突（如 `__init__.py` 中导出 API 的 `F401`）。
- 修复代价与收益不成比例（如遗留代码的大规模重构）。
- 抑制范围窄（单行单规则 `# noqa: F401`，非文件级 `# noqa` 或裸 `# noqa`）。

不满足条件时，优先修复代码而非抑制。

## 无进展检测

- 连续两轮无新修复时停止循环。
- 记录剩余未修复项，向用户报告并说明原因。

## 执行规范

- 传递目录作为参数（`ruff check src/`），不切换工作目录。
- 格式化先于 lint（`ruff format src/ && ruff check src/`）。
- 项目无 ruff 配置时不主动引入，沿用现有工具链。
