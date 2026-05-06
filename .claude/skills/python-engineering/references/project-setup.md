# 项目设置

> 本文件范围：Python 项目初始化与配置模式（目录结构、pyproject.toml、关键决策、pre-commit）。
> 不在本文件范围：CI/CD 流水线设计、Docker 容器化、复杂构建系统。

## 推荐目录结构

使用 `src/` 布局，防止意外导入开发代码：

```
my-project/
├── src/
│   └── my_package/
│       ├── __init__.py
│       └── py.typed          # 标记为类型友好包
├── tests/
├── pyproject.toml
└── README.md
```

## 最小 pyproject.toml

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "my-package"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest", "ruff", "mypy"]

[tool.setuptools.packages.find]
where = ["src"]
```

## 关键决策表

| 选择 | 推荐 | 理由 |
|---|---|---|
| 布局 | `src/` | 尽早发现打包错误 |
| 构建后端 | setuptools | 成熟、兼容性广 |
| Linter | ruff | 快速，替代 flake8+isort+black |
| Python 版本 | `>=3.10` | 不锁定精确版本 |
| 依赖 | 最小化 | 可选依赖放 extras |

## pre-commit 基础

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: <latest-compatible-ruff-pre-commit-version>
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

新增配置前查询当前最新版本或沿用项目现有版本。

## 常用命令

```bash
pip install -e ".[dev]"     # 开发模式安装
ruff check src tests        # Lint
ruff format src tests       # Format
pytest                      # 测试
mypy src                    # 类型检查
```
