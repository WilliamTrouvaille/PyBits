# CLI 开发

> 本文件范围：Python CLI 开发模式（框架选择、入口点、常用模式、测试）。
> 不在本文件范围：Shell completion 配置、子进程管理、GUI 框架。

## 框架选择

| 框架 | 特点 | 适合场景 |
|---|---|---|
| Click | 成熟、功能全、装饰器驱动 | 中大型 CLI，需要命令组/选项 |
| Typer | 现代、类型提示驱动、基于 Click | 偏好类型标注的项目 |
| argparse | 零依赖、stdlib 内置 | 简单脚本，不想加依赖 |

## 入口点配置

在 `pyproject.toml` 中声明：

```toml
[project.scripts]
mycli = "my_package.cli:cli"
```

安装后即可直接使用 `mycli` 命令。

## 常用模式

### 文件 I/O

```python
@click.command()
@click.argument("input", type=click.File("r"), default="-")
@click.argument("output", type=click.File("w"), default="-")
def process(input, output):
    output.write(input.read())
```

`default="-"` 支持 stdin/stdout 管道。

### 进度条

```python
with click.progressbar(items, label="Processing") as bar:
    for item in bar:
        process(item)
```

### 彩色输出

```python
click.secho("Success!", fg="green")
click.secho("Error!", fg="red", bold=True)
```

### 错误处理

```python
@click.command()
@click.option("--count", type=int, required=True)
def cmd(count):
    if count < 0:
        raise click.BadParameter("Count must be non-negative", param_hint="--count")
```

## CliRunner 测试

```python
from click.testing import CliRunner

def test_process():
    runner = CliRunner()
    result = runner.invoke(cli, ["process", "input.txt"])
    assert result.exit_code == 0
    assert "Done" in result.output

def test_stdin():
    runner = CliRunner()
    result = runner.invoke(cli, ["process"], input="hello")
    assert "hello" in result.output
```

## 检查清单

- [ ] 入口点：`pyproject.toml` `[project.scripts]` 已配置
- [ ] `--help` 和 `--version` 可用
- [ ] 错误信息输出到 stderr，用户可读
- [ ] 所有命令和错误路径有测试
