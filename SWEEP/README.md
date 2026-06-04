# SWEEP

SWEEP 扫描配置中的 Cleanup Scope，生成实时 Cleanup Candidate 清单，并将过期临时文件或项目临时目录移动到系统 trash。`trash` 不可用或单个候选移动失败时，SWEEP 会退回到 `.codex/_trash_bin_` 体系内的 soft-delete fallback；仍无法处理的路径会追加写入 `SWEEP/_cache/unresolved_failures.jsonl`。

## 用法

```bash
SWEEP
SWEEP --dry-run
SWEEP --dry-run --json
SWEEP --config /path/to/fixture.yaml --json
```

默认配置位于 `SWEEP/setting.yaml`，缓存和审计状态位于 `SWEEP/_cache/`。直接执行 `SWEEP` 会打印完整 Cleanup Candidate 清单，然后执行移动并输出摘要。

## 候选分类

- `whole_dir`：项目清理范围内整棵临时目录树都过期时，移动目录本身。
- `partial_items`：只移动目录树中符合规则的部分文件或目录；清理后变空的目录也归入这一类后续处理。

`~/TEMP` 和 `~/Downloads` 这类范围只产生文件候选，不移动目录本身，也不清理空目录。
