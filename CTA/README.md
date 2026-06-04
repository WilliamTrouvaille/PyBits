# CTA

CTA 用于从当前工作目录的 `CLAUDE.md` 生成 `AGENTS.md`，适合把 Claude Code 项目指令转换为 OpenAI Codex 项目指令。

## 安装

在 PyBits 项目根目录刷新全局命令：

```bash
uv tool install --force --reinstall --refresh .
```

安装后，可在任意目录直接使用 `CTA`。

## 使用示例

```bash
CTA
CTA --force
```

`CTA` 不接收输入文件或输出目录参数。它始终读取当前工作目录下的 `CLAUDE.md`，并写入同一目录下的 `AGENTS.md`。

## 转换规则

CTA 只执行字面文本替换，不解析 Markdown 或项目结构：

- `Claude` 替换为 `Codex`
- `.claude/` 替换为 `.codex/`

替换区分大小写；例如 `claude`、`CLAUDE` 或其他变体不会被替换。源文件 `CLAUDE.md` 不会被修改或删除。

## 覆盖规则

- 如果当前目录没有 `CLAUDE.md`，命令返回非 0，并在 stderr 输出 `ERROR: CLAUDE.md not found ...`。
- 如果 `AGENTS.md` 不存在，命令写入新文件，并在 stdout 输出创建路径。
- 如果 `AGENTS.md` 已存在，或存在断开的 `AGENTS.md` 符号链接，且未使用 `--force`，命令返回非 0，不写入新文件。
- 使用 `--force` 时，已存在的 `AGENTS.md` 会先 soft-delete，再写入新的 `AGENTS.md`。

soft-delete 会把旧文件移动到最近的 `.codex/_trash_bin_/` 下，文件名包含时间戳和 `cta-force-agents` 标记；如果当前目录及其父目录没有 `.codex/`，则会在当前工作目录创建 `.codex/_trash_bin_/`。

## 限制

- `CTA` 会先写入临时文件，确认临时文件写入成功后再处理既有 `AGENTS.md`。
- `--force` 仍会先 soft-delete 旧 `AGENTS.md`，再把临时文件替换到目标路径；如果最终替换阶段失败，需要从 `.codex/_trash_bin_/` 手动恢复旧文件。
- 该工具不校验生成后的指令语义，只保证执行上述两个字面替换。
