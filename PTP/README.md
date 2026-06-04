# PTP

PTP 是一个基于 PyMuPDF 的 PDF 转 PNG 命令行工具。它在本地渲染 PDF 页面，不依赖系统 `poppler`。

## 安装

在 PyBits 项目根目录执行：

```bash
uv tool install --force --reinstall --refresh .
```

安装后，可在任意目录直接使用全局命令 `PTP`。

## 使用示例

```bash
PTP input.pdf
PTP input.pdf --dpi 200
PTP input.pdf --page 1
PTP input.pdf --pages 1,3-5
PTP input.pdf --out-dir ./out
PTP input.pdf --force
```

转换成功时，stdout 输出生成的 PNG 文件绝对路径；多页转换会每行输出一个路径。

## 参数说明

```text
PTP input.pdf [OPTIONS]

必填参数:
  input_pdf              输入 PDF 文件路径

可选参数:
  --dpi DPI              渲染 DPI，默认 200
  --page PAGE            只渲染单个页码，页码从 1 开始
  --pages PAGES          渲染页码范围，例如 "1,3-5"
  --out-dir DIR          输出目录，默认按输入 PDF 自动决定
  --format {png}         输出格式，当前仅支持 png
  --force                若目标文件已存在，先软删除旧文件再覆盖
  -v, --verbose          显示详细日志
  -h, --help             显示帮助信息
```

`--page` 与 `--pages` 互斥，页码均为 PDF 原始页码，且从 1 开始。`--pages` 会按输入顺序渲染，并跳过重复页码；例如 `1,3-5,3,2` 会输出第 1、3、4、5、2 页。

## 输出规则

- 单页 PDF 默认输出到 PDF 同目录：`input.png`。
- 多页 PDF 默认输出到 PDF 同根目录下的 `input_PTP/` 文件夹；即使只用 `--page` 选择其中一页，也仍按多页 PDF 命名。
- 多页 PDF 或选定页码的输出文件名为原始页码：`input_001.png`、`input_003.png`。编号不是输出顺序，而是 PDF 页码。
- 指定 `--out-dir` 时，所有输出文件直接写入该目录，不再自动创建 `input_PTP/` 子目录；文件名规则保持不变。
- 目标文件已存在时默认报错，且不会写入新文件；指定 `--force` 后，旧文件会先移动到 `.codex/_trash_bin_/` 再写入新文件。
- soft-delete 会从目标文件所在位置向上查找最近的 `.codex/_trash_bin_/`；如果找不到 `.codex/`，则使用当前工作目录下的 `.codex/_trash_bin_/`。

## 错误格式

文件、输出路径、PDF 渲染等可预期运行错误会输出为：

```text
ERROR: Output file already exists: /path/to/input.png
HINT: Use --force to soft-delete the old file before writing a new one.
```

参数解析错误使用 `argparse` 的标准格式，通常包含 `usage:` 和 `PTP: error: ...`。例如 `--dpi 0` 或非法 `--pages` 会在开始渲染前失败。
