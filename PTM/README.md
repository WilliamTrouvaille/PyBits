# PTM

PTM 是一个基于 MinerU 精准解析 API 的 PDF 转 Markdown 命令行工具。它不会在本地运行 MinerU 模型；执行流程是上传本地 PDF、等待 MinerU 解析、下载结果 zip，并将其中的 `full.md` 提取为带时间戳的 Markdown 文件。

## 使用前准备

- 使用本 PyBits 项目的 Python 环境。
- 在 [mineru.net](https://mineru.net) 获取 MinerU API Token。
- 输入 PDF 文件大小不超过 200MB。
- 本地预检按约 600 页限制估算页数。MinerU 服务端可能根据当前 API 策略执行更严格的限制，以服务端返回为准。

## Token 配置

本项目不使用系统环境变量。PTM 只从 `PTM/.env` 读取 Token：

```dotenv
MINERU_API_TOKEN=your_api_token_here
```

`PTM/.env` 已被 git 忽略，请不要提交 API Token。

全局安装后，从任意目录运行 `PTM` 时，工具会优先查找当前目录及其父目录下的 `PTM/.env`；如果不在项目目录内运行，会读取本机 PyBits 仓库中的 `/Users/trouva/CODE/PYTHON/PyBits/PTM/.env`。

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
  --timeout SECONDS      总轮询超时时间，默认 300 秒
  --poll-interval SEC    轮询间隔，默认 3 秒
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

启用 `--images` 时，PTM 会把 MinerU 结果中的 `images/` 目录复制到输出目录。如果输出目录已存在 `images/`，PTM 会停止并给出提示，不会覆盖已有目录。

未启用 `--keep-zip` 时，PTM 会在成功提取 Markdown 后删除下载的结果 zip。

## 错误格式

可预期错误统一输出为：

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

## 安全说明

- 不会打印签名上传 URL 或下载 URL。
- 日志中的 API Token 会脱敏。
- 上传到 MinerU 签名 URL 时不会附带 Authorization header。
