# PTM

PTM 是一个基于 MinerU 精准解析 API 的 PDF 转 Markdown 命令行工具。它不会在本地运行 MinerU 模型；执行流程是上传本地 PDF、等待 MinerU 解析、下载结果 zip，并将其中的 `full.md` 提取为带时间戳的 Markdown 文件。

## 使用前准备

- 使用本 PyBits 项目的 Python 环境。
- 在 [mineru.net](https://mineru.net) 获取 MinerU API Token。
- 输入 PDF 文件大小不超过 200MB。
- 本地预检按约 600 页限制估算页数。MinerU 服务端可能根据当前 API 策略执行更严格的限制，以服务端返回为准。

## Token 配置

PTM 不读取系统环境变量，只从文件系统里的 `PTM/.env` 读取 Token：

```dotenv
MINERU_API_TOKEN=your_api_token_here
```

`PTM/.env` 已被 git 忽略，请不要提交 API Token。

全局安装后，从任意目录运行 `PTM` 时，工具按以下顺序查找第一个存在的 `.env`：

1. 当前工作目录及其每一级父目录下的 `PTM/.env`。
2. `~/CODE/PYTHON/PyBits/PTM/.env`。
3. 已安装或当前源码包旁边的 `PTM/.env`。

如果找到 `.env` 但没有 `MINERU_API_TOKEN`，PTM 会继续按“缺少 Token”处理，并在错误提示里显示本次尝试读取的 `.env` 路径。

## 安装

在 PyBits 项目根目录执行：

```bash
uv tool install --force --reinstall --refresh .
```

安装后，可在任意目录直接使用全局命令 `PTM`。

## 使用示例

```bash
PTM input.pdf
PTM input.pdf --out-dir ./output
PTM input.pdf --ocr --images --keep-zip
PTM input.pdf --page-ranges "2,4-6"
PTM input.pdf --proxy http://127.0.0.1:7890
PTM input.pdf --download-retries 6 --download-backoff 3
```

转换成功时，stdout 只输出最终 Markdown 文件路径：

```text
/path/to/input_PTM_20260515_153000.md
```

日志、进度和错误信息输出到 stderr。

## 参数说明

```text
PTM input.pdf [OPTIONS]

必填参数:
  input_pdf              输入 PDF 文件路径

可选参数:
  --out-dir DIR          输出目录，默认与输入 PDF 同目录
  --timeout SECONDS      总轮询超时时间，必须大于 0，默认 300 秒
  --poll-interval SEC    轮询间隔，必须大于 0，默认 3 秒
  --download-retries N   首次下载失败后的重试次数，必须不小于 0，默认 4
  --download-backoff SEC 下载重试的初始退避秒数，必须不小于 0，默认 2.0
  --model-version VER    模型版本：pipeline、vlm 或 MinerU-HTML，默认 vlm
  --lang LANG            语言代码，默认 ch
  --images               保留 MinerU 结果中的 images/ 目录
  --ocr                  启用 OCR
  --table                启用表格识别，默认启用
  --no-table             禁用表格识别
  --formula              启用公式识别，默认启用
  --no-formula           禁用公式识别
  --page-ranges RANGES   页码范围，例如："2,4-6"
  --proxy URL            HTTP(S) 代理 URL
  --keep-zip             保留下载的结果 zip 文件
  -v, --verbose          显示详细日志
  -h, --help             显示帮助信息
```

## 输出规则

默认输出到输入 PDF 所在目录。Markdown 文件名格式为：

```text
<input_name>_PTM_YYYYMMDD_HHMMSS.md
```

启用 `--images` 时，PTM 会把 MinerU 结果中的 `images/` 目录复制到输出目录。如果输出目录已存在 `images/`，PTM 会在解压前停止并给出提示，不会覆盖已有目录，也不会先写出 Markdown。

启用 `--keep-zip` 时，结果 zip 会保留在输出目录中，文件名与 Markdown 的 stem 相同。未启用 `--keep-zip` 时，PTM 会在成功提取 Markdown 后把下载的结果 zip 软删除到最近的 `.codex/_trash_bin_/`；如果运行目录附近没有 `.codex`，则使用当前工作目录下的 `.codex/_trash_bin_/`。

下载结果 zip 时，PTM 会先写入同目录下的 `.part` 临时文件。同一次命令内，如果下载失败但仍有重试次数，下一次下载尝试会通过 HTTP `Range` 从已完成字节继续。下载失败后，PTM 会按指数退避重试，并在每次可重试失败后使用已有 `batch_id` 重新拉取 MinerU 结果 zip URL，避免临时 CDN URL 失效导致整次任务作废。重新运行一条新的 `PTM input.pdf` 命令会生成新的时间戳文件名，不会自动续用上一次命令留下的 `.part`。

解压结果 zip 前，PTM 会检查 zip 内路径是否包含绝对路径或 `..`，并限制解压后的总大小不超过 1GB。zip 中没有 `full.md` 时，命令会失败；启用 `--images` 但 zip 中没有 `images/` 目录时，命令只会在 stderr 写入警告，Markdown 仍会正常生成。

## 错误格式

PTM 运行时可预期错误输出为：

```text
ERROR: File not found: missing.pdf
HINT: Check the file path and try again.
```

常见处理方式：

- 缺少 Token：在 `PTM/.env` 中填写 `MINERU_API_TOKEN=...`。
- Token 无效：在 MinerU 重新获取 API Token，并更新 `PTM/.env`。
- 文件过大：拆分或压缩 PDF。
- 页数过多：拆分 PDF，或使用 `--page-ranges` 处理部分页码。
- 轮询超时：对复杂 PDF 增大 `--timeout`。
- 下载失败：先尝试 `--proxy`；必要时增大 `--download-retries` 或 `--download-backoff`。

参数解析错误沿用 `argparse` 默认格式，会输出 `usage: ...` 和 `PTM: error: ...`，不使用上面的 `ERROR` / `HINT` 两行格式。

## 安全说明

- 常规日志不会主动打印签名上传 URL 或下载 URL；网络异常会对请求 URL 做脱敏后再输出。
- 日志中的 API Token 会脱敏。
- 上传到 MinerU 签名 URL 时不会附带 Authorization header。
- PTM 不在本地运行 MinerU 模型；输入 PDF 会上传到 MinerU 服务端处理。
