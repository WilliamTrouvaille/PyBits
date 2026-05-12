# PTM - PDF to Markdown

PTM 是一个基于 MinerU 的 PDF 转 Markdown 工具，支持自动模型下载、超时控制和图片提取。

## 功能特性

- 🚀 自动检测并下载 MinerU 模型（首次运行）
- ⏱️ 可配置的超时控制（默认 5 分钟）
- 🖼️ 可选的图片提取功能
- 📝 规范化的输出文件命名（带时间戳）
- 🔍 严格的输入验证（PDF 格式检查、权限检查）
- 📊 实时进度反馈（rich spinner）
- 🛡️ 完善的错误处理和提示

## 安装

### 1. 安装依赖

```bash
cd /Users/trouva/CODE/PYTHON/PyBits
uv sync --extra ptm
```

### 2. 预下载模型（推荐）

首次使用前建议预下载模型（约 1-2GB）：

```bash
# 使用国内源（推荐）
magic-pdf --download-models --model-source modelscope

# 使用代理（可选）
magic-pdf --download-models --model-source modelscope --proxy http://127.0.0.1:7890

# 验证模型是否下载成功
ls -lh ~/.cache/modelscope/hub/
```

模型会下载到 `~/.cache/modelscope/hub/`。如果不预下载，首次运行时会自动下载。

## 使用方法

### 基本用法

```bash
# 最简单的用法（输出到输入文件同目录）
PTM input.pdf

# 指定输出目录
PTM input.pdf --out-dir /path/to/output

# 启用图片提取
PTM input.pdf --images

# 设置超时时间（秒）
PTM input.pdf --timeout 600

# 使用代理
PTM input.pdf --proxy http://127.0.0.1:7890
```

### 完整参数

```bash
PTM input.pdf \
  [--out-dir /path/to/run-dir] \
  [--images] \
  [--engine mineru] \
  [--timeout 300] \
  [--model-source modelscope] \
  [--proxy <proxy_address>]
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input.pdf` | 必须 | 输入 PDF 文件路径 |
| `--out-dir` | 输入文件同目录 | 输出目录 |
| `--images` | False | 是否输出图片到 `imgs/` 文件夹 |
| `--engine` | mineru | 转换引擎（当前仅支持 mineru） |
| `--timeout` | 300 | 超时时间（秒） |
| `--model-source` | modelscope | 模型源（modelscope/huggingface） |
| `--proxy` | None | 代理地址 |
| `--help` | - | 显示帮助信息 |

## 输出格式

### 文件命名

输出文件名格式：`<input_name>_PTM_YYYYMMDD_HHMMSS.md`

示例：
- 输入：`paper.pdf`
- 输出：`paper_PTM_20260507_143022.md`

### 目录结构

#### 不启用图片（默认）

```
/path/to/output/
  paper_PTM_20260507_143022.md
```

#### 启用图片（--images）

```
/path/to/output/
  paper_PTM_20260507_143022.md
  imgs/
    fig_001.png
    fig_002.png
```

Markdown 文件中的图片引用格式：`![](./imgs/fig_001.png)`

## 契约规范

### 成功（exit 0）

- **输出文件**：`<input_name>_PTM_YYYYMMDD_HHMMSS.md`
- **stderr**：包含 INFO/WARN/MinerU 原始日志
- **stdout**：空

### 失败（exit 1）

- **stderr**：包含完整日志，最后以 `ERROR:` 或 `HINT:` 收束
- **stdout**：空

示例：
```
[INFO] 开始处理 input.pdf...
[ERROR] 文件不存在: /path/to/input.pdf
ERROR: 无法读取输入文件
HINT: 请检查文件路径是否正确
```

## 错误处理

| 错误类型 | ERROR 信息 | HINT 信息 |
|----------|-----------|-----------|
| 文件不存在 | `ERROR: 无法读取输入文件` | `HINT: 请检查文件路径是否正确` |
| 非 PDF 文件 | `ERROR: 输入文件不是有效的 PDF` | `HINT: 请提供 .pdf 格式的文件` |
| 输出文件已存在 | `ERROR: 输出文件已存在` | `HINT: 请删除现有文件或更改输出目录` |
| 输出目录不可写 | `ERROR: 输出目录无写入权限` | `HINT: 请检查目录权限或更改输出目录` |
| imgs/ 已存在 | `ERROR: imgs/ 文件夹已存在` | `HINT: 请删除现有文件夹或禁用 --images` |
| 超时 | `ERROR: 转换超时（{timeout}秒）` | `HINT: 尝试增加 --timeout 参数或检查 PDF 文件大小` |
| MinerU 失败 | `ERROR: MinerU 转换失败` | `HINT: 请查看上方日志了解详细错误信息` |

## 使用示例

### 示例 1：转换单个 PDF

```bash
PTM ~/Documents/paper.pdf
```

输出：
```
[INFO] 输入文件: /Users/trouva/Documents/paper.pdf
[INFO] 输出目录: /Users/trouva/Documents
[INFO] 输出文件: paper_PTM_20260507_143022.md
[INFO] 图片输出: 禁用
[INFO] 超时时间: 300 秒
[INFO] 模型已存在: /Users/trouva/.cache/modelscope/hub
[INFO] 开始转换 PDF: /Users/trouva/Documents/paper.pdf
[INFO] 转换完成: /Users/trouva/Documents/paper_PTM_20260507_143022.md
[INFO] 转换成功完成
```

### 示例 2：转换并提取图片

```bash
PTM ~/Documents/paper.pdf --images --out-dir ~/Desktop/output
```

输出结构：
```
~/Desktop/output/
  paper_PTM_20260507_143022.md
  imgs/
    fig_001.png
    fig_002.png
```

### 示例 3：大文件转换（增加超时）

```bash
PTM large_paper.pdf --timeout 1200
```

## 注意事项

1. **模型下载**：首次运行会自动下载模型（约 1-2GB），需要网络连接和足够磁盘空间
2. **超时设置**：大型 PDF 可能需要更长时间，建议根据文件大小调整 `--timeout` 参数
3. **输出文件冲突**：如果输出文件已存在，程序会报错退出，不会覆盖现有文件
4. **图片文件夹冲突**：启用 `--images` 时，如果 `imgs/` 文件夹已存在，程序会报错退出

## 技术细节

### 依赖

- `magic-pdf[full]>=1.3.12,<1.4`：MinerU 核心库与 full extra 依赖
- `loguru>=0.7.3`：日志管理
- `rich>=13.0.0`：终端 UI（spinner）

### 超时控制

- 超时后发送 SIGTERM 给 MinerU 进程
- 等待 5 秒优雅退出
- 仍未退出则 SIGKILL 强制终止
- 自动清理临时文件

### 参数验证

在调用 MinerU 之前进行以下检查：

1. **输入文件验证**：
   - 文件存在
   - 文件可读
   - 文件格式为 PDF（检查 magic number `%PDF`）

2. **输出目录验证**：
   - 输出目录可写
   - 输出文件不存在
   - `imgs/` 文件夹不存在（启用 `--images` 时）

3. **参数验证**：
   - `--engine` 只接受 `mineru`
   - `--timeout` 必须为正整数
   - `--model-source` 只接受 `modelscope` 或 `huggingface`

## 故障排查

### 问题：magic-pdf 命令未找到

```bash
ERROR: magic-pdf 命令未找到
HINT: 请先安装 magic-pdf: pip install magic-pdf[full]
```

**解决方法**：
```bash
uv sync --extra ptm
```

### 问题：模型下载失败

```bash
ERROR: 模型检查或下载失败
HINT: 请检查网络连接或手动运行 magic-pdf --download-models
```

**解决方法**：
```bash
# 手动下载模型
magic-pdf --download-models --model-source modelscope

# 如果需要代理
magic-pdf --download-models --model-source modelscope --proxy http://127.0.0.1:7890
```

### 问题：转换超时

```bash
ERROR: 转换超时（300秒）
HINT: 尝试增加 --timeout 参数或检查 PDF 文件大小
```

**解决方法**：
```bash
# 增加超时时间到 10 分钟
PTM input.pdf --timeout 600
```

## 许可证

本项目为个人工具集合的一部分，仅供学习和个人使用。
