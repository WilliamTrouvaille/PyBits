---
name: python-engineering
description: "Python code and Python project engineering guidance for implementation, debugging, refactoring, review, linting, formatting, typing, testing, project setup, CLI development, library API design, and PyTorch training engineering. Use when the user asks to write, modify, debug, refactor, review, or quality-check Python code or Python project files, including pyproject.toml, pytest, ruff, mypy/pyright, Python CLI tools, Python library APIs, or PyTorch training code. Triggers: Python, write, implement, code, modify, fix, debug, refactor, review, pytest, ruff, typing, CLI, API design, project setup, PyTorch training, 写, 编写, 实现, 编码, 改, 修改, 审查, 深度学习, 模型训练, 类型检查, 格式化, 命令行"
---

# Python Engineering

## 核心规则

- 优先遵循当前仓库的指令文件（`AGENTS.md`、`CLAUDE.md` 等），本 skill 仅在项目规则未覆盖处生效。
- 以下路径相对于本 skill 目录，而非当前仓库根目录。

## 职责边界

| 本 skill 负责 | 应委托给其他 skill/工具 |
|---|---|
| Python 代码编写/修改/审查 | 非 Python 语言任务 |
| ruff lint/format 工作流 | 其他 linter/formatter 配置 |
| Python 类型标注与迁移 | 非 Python 类型系统（TypeScript 等） |
| DL/ML 训练工程实践 | DL 算法设计/模型架构选择 |
| Python 项目配置、CLI、API 设计 | CI/CD 流水线设计、安全审计 |

## 模式选择

Python 任务默认使用**写代码模式**：读取 `references/python-standards.md` + `references/writing-workflow.md`，做最小有效改动并验证。

仅当用户明确要求审查/审计时使用**审查模式**：读取 `references/python-standards.md` + `references/review-workflow.md`，仅检查不编辑。

模式歧义时按措辞推断：
- 写代码：fix, implement, add, change, debug, refactor, 写, 编写, 实现, 修改
- 审查：review, audit, look over, 审查, 只看不改

## 条件加载

根据任务关键词，在必读参考之外额外加载：

| 触发关键词 | 额外读取 |
|---|---|
| PyTorch training, training loop, DataLoader, checkpoint, torch.amp, training code, 模型训练代码, PyTorch 训练 | `references/dl-ml-engineering.md` |
| typing, type hints, pyright, mypy, 类型检查, 类型标注 | `references/typing-guide.md` |
| ruff, lint, format, 格式化, 代码规范 | `references/ruff-workflow.md` |
| project setup, pyproject.toml, 项目设置, 新建项目 | `references/project-setup.md` |
| CLI, Click, Typer, argparse, 命令行 | `references/cli-development.md` |
| API design, API 设计, library design | `references/api-design.md` |
| pytest, testing pattern, 测试策略 | `references/testing-guide.md` |

多个条件可同时触发（如"搭建带类型的 CLI 项目"会加载 writing-workflow + typing-guide + cli-development + project-setup）。

## 工作原则

- 解决方案规模与问题相匹配。
- 优先沿用项目现有模式、工具和结构。
- 审查时不将个人风格偏好上升为缺陷。
- 无法运行验证时，明确说明未运行的内容及原因。
