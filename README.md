# PyBits

独立 Python 小工具集合。每个工具放在独立目录中，通过统一 `uv` 环境管理依赖，并在 `pyproject.toml` 的 `[project.scripts]` 中注册为全局命令。

## 工具列表

| 命令 | 用途 |
| --- | --- |
| `AIM` | 只读索引 Claude Code / Codex 会话、日志和 memory 文本，输出候选记忆。 |
| `ATP` | 下载并转换 arXiv 论文 LaTeX 源码。 |
| `CTA` | 从当前目录的 `CLAUDE.md` 生成 `AGENTS.md`。 |
| `HELLO` | 探测 Claude Code 和 Codex CLI 连通性。 |
| `PTM` | 通过 MinerU API 将 PDF 转换为 Markdown。 |
| `PTP` | 使用 PyMuPDF 将 PDF 页面渲染为 PNG 图片。 |
| `SKILLS` | 管理 Claude Code / Codex skill 仓库、扫描、安装和更新。 |

## 安装刷新

修改代码、入口或依赖后，刷新全局命令：

```bash
uv tool install --force --reinstall --refresh .
```

常用本地执行方式：

```bash
uv run HELLO --help
uv run SKILLS --help
uv run PTM --help
uv run PTP --help
uv run ATP --help
uv run AIM --help
uv run CTA --help
```

## 校验

共享结构检查：

```bash
uv run python _shared/tests/basic_info_check.py
```

全局命令检查会刷新已安装工具，并在项目外目录执行 `--help` 和未知参数负例：

```bash
uv run python _shared/tests/global_command_check.py
```

## 项目约定

- 工具目录使用 `UPPER-KEBAB-CASE`，入口为 `<TOOL_NAME>/cli.py`。
- 工具内部 Python 文件使用 `snake_case.py`。
- 依赖统一写入 `pyproject.toml`，脚本内不使用 inline dependency。
- 共享代码放在 `_shared/`，共享测试放在 `_shared/tests/`。
- 不执行不可逆删除；需要清理或覆盖时，移动到 `.codex/_trash_bin_/`。
- 工具日志默认写入各工具的 `logs/` 目录。
