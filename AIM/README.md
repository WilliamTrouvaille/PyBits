# AIM

Agent Index Memory.

`AIM` 只读扫描本机 Claude Code / Codex 会话、日志和 memory 文本，生成可追溯索引与候选记忆。工具不会写入任何 memory 文件。

## 用法

```bash
AIM
AIM --claude-home ~/.claude --codex-home ~/.codex
AIM --since 2026-05-01 --limit 200 --out-dir ./aim-out
```

## 输出

- `index.json`：结构化索引记录。
- `candidates.md`：候选记忆清单，包含来源、时间、置信度和推荐动作。
- `evidence/`：脱敏后的证据摘录。

默认会脱敏 API key、token、cookie、Authorization 头和邮箱地址。
