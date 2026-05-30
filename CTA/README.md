# CTA - Claude to Agents

Create `AGENTS.md` from the `CLAUDE.md` file in the current directory.

## Usage

```bash
CTA
```

The command reads `./CLAUDE.md`, replaces `Claude` with `Codex`, replaces `.claude/` with `.codex/`, and writes `./AGENTS.md`.

By default, an existing `AGENTS.md` is not overwritten. Use `--force` only when overwriting is intended:

```bash
CTA --force
```
