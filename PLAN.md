# PTM (PDF to Markdown) 实现计划

## Context

PTM 是一个基于 MinerU 精准解析 API 的 PDF 转 Markdown 工具。用户需要一个命令行工具，能够通过 HTTPS API 调用 MinerU 服务（https://mineru.net/apiManage/docs），将本地 PDF 文件转换为 Markdown 格式，无需本地安装模型。

**为什么需要这个工具**：
- 避免本地部署 MinerU 模型的复杂性和资源消耗
- 提供简单的 CLI 接口，支持批量处理和自动化
- 统一的错误处理和用户友好的提示信息
- 作为 PyBits 工具集的一部分，提供全局命令支持

**关键约束**：
- 文件大小限制：200MB
- 页数限制：600 页
- Token 认证：支持 CLI 参数、环境变量、.env 文件三种方式
- 输出格式：`<input_name>_PTM_YYYYMMDD_HHMMSS.md`

## 目录结构

```
PTM/
├── README.md                    # 项目文档
├── cli.py                       # CLI 入口（必须符合项目规范）
├── .env                         # Token 配置文件（可选，用户创建）
├── src/                         # 源代码目录（必须）
│   ├── __init__.py
│   ├── api_client.py           # MinerU API 客户端
│   ├── pdf_validator.py        # PDF 文件校验
│   ├── file_handler.py         # zip 下载和解压
│   ├── config.py               # 配置和 Token 管理
│   ├── models.py               # 数据模型（异常类）
│   └── constants.py            # 常量定义
└── logs/                        # 日志目录（自动创建）
```

## 技术选型

**使用现有依赖**（无需新增）：
- `requests`：HTTP 客户端，用于 API 调用和文件上传下载
- `loguru`：日志管理
- `rich`：进度条显示
- `argparse`（标准库）：CLI 参数解析
- `zipfile`（标准库）：zip 文件解压
- `pathlib`（标准库）：路径处理

## 实现步骤

### 1. 创建基础结构

**文件**：
- `PTM/README.md`：项目文档，包括安装、使用、API Token 获取说明
- `PTM/cli.py`：CLI 入口，包含 `main()` 函数
- `PTM/src/__init__.py`：空文件
- `PTM/src/constants.py`：常量定义
- `PTM/src/models.py`：`PTMError` 异常类

**关键点**：
- 遵循项目规范：目录名 UPPER-KEBAB-CASE，Python 文件 snake_case
- CLI 入口必须是 `cli.py` 中的 `main()` 函数

### 2. 实现配置管理（PTM/src/config.py）

**功能**：
- `load_token(cli_token: str | None) -> str`：按优先级加载 Token
  1. CLI 参数 `--token`
  2. 环境变量 `MINERU_API_TOKEN`
  3. `PTM/.env` 文件中的 `MINERU_API_TOKEN=xxx`
- `mask_token(token: str) -> str`：脱敏 Token 用于日志（显示前 4 位和后 4 位）

**错误处理**：
- 无 Token 时抛出 `PTMError`，提示三种配置方式

### 3. 实现 PDF 校验（PTM/src/pdf_validator.py）

**功能**：
- `validate_pdf(pdf_path: str) -> Path`：校验 PDF 文件
  1. 文件存在性
  2. 是文件（非目录）
  3. 可读性
  4. PDF magic number（`%PDF-`）
  5. 文件大小 ≤ 200MB
  6. 页数估算 ≤ 600 页（使用正则表达式搜索 `/Count` 字段）

**关键实现**：
```python
def estimate_pdf_pages(pdf_path: Path) -> int:
    """估算 PDF 页数（不引入额外依赖）"""
    content = pdf_path.read_bytes()
    # 查找 /Count 字段
    match = re.search(rb"/Count\s+(\d+)", content)
    if match:
        return int(match.group(1))
    # 备用：统计 /Type /Page 出现次数
    return max(content.count(b"/Type /Page"), 1)
```

**错误处理**：
- 每种校验失败都有对应的 `ERROR` + `HINT` 信息
- 无法估算页数时记录 WARNING，不阻断流程

### 4. 实现 API 客户端（PTM/src/api_client.py）

**类**：`MinerUAPIClient`

**方法**：
1. `__init__(token: str, proxy: str | None)`：初始化 requests.Session，设置 Authorization header
2. `create_batch_task(...) -> tuple[str, str]`：
   - POST `/api/v4/file-urls/batch`
   - 返回 `(batch_id, signed_upload_url)`
3. `upload_file(signed_url: str, pdf_path: Path) -> None`：
   - PUT 上传到签名 URL
   - 不需要 Authorization header
   - Content-Type: application/pdf
4. `poll_result(batch_id: str, timeout: int, poll_interval: int) -> str`：
   - GET `/api/v4/extract-results/batch/{batch_id}`
   - 轮询状态：`waiting-file`, `pending`, `running`, `converting`, `done`, `failed`
   - 使用 `rich.progress` 显示进度
   - 返回 `full_zip_url`
5. `_check_response(resp: requests.Response) -> None`：
   - 统一错误码处理
   - 特殊处理：A0202/A0211（Token），-60005（文件过大），-60006（页数超限）

**关键点**：
- 日志中不打印完整 Token 或签名 URL
- 超时处理：单次请求 30 秒，总轮询时间由用户指定
- 使用 `rich.progress.Progress` 显示轮询进度

### 5. 实现文件处理（PTM/src/file_handler.py）

**功能**：
1. `download_zip(url: str, dest_path: Path) -> None`：
   - 使用 `requests.get(stream=True)` 下载
   - 使用 `rich.progress` 显示下载进度
2. `extract_markdown(zip_path: Path, out_dir: Path, output_name: str, keep_images: bool, keep_zip: bool) -> Path`：
   - 安全检查：防止 zip bomb（解压后总大小 < 1GB）
   - 解压到临时目录 `_temp_{output_name}`
   - 查找 `full.md`（应在根目录）
   - 复制到最终位置：`{output_name}.md`
   - 如果 `keep_images=True`，复制 `imgs/` 目录
   - 清理临时目录
   - 如果 `keep_zip=False`，删除 zip 文件

**错误处理**：
- zip 过大：提示联系支持
- 找不到 `full.md`：提示联系支持
- `imgs/` 目录已存在：提示删除或禁用 `--images`

### 6. 实现 CLI 入口（PTM/cli.py）

**函数**：
1. `build_parser() -> argparse.ArgumentParser`：
   - 定义所有 CLI 参数
   - `--table` 和 `--formula` 默认为 True，提供 `--no-table` 和 `--no-formula` 选项
2. `setup_logger(verbose: bool) -> None`：
   - 配置 loguru，日志输出到 stderr
   - 格式：`{time:HH:mm:ss} | {level} | {message}`
3. `prepare_output_dir(input_pdf: str, out_dir: str | None) -> Path`：
   - 确定输出目录（默认输入文件同目录）
   - 创建目录（如果不存在）
4. `convert_pdf_via_api(...) -> Path`：
   - 主流程：创建任务 → 上传 → 轮询 → 下载 → 解压
5. `main() -> int`：
   - 解析参数
   - 调用各模块
   - 统一错误处理：`PTMError` 输出 `ERROR` + `HINT`，其他异常输出堆栈
   - 成功时输出最终文件路径到 stdout
   - 返回退出码：0（成功）或 1（失败）

**关键点**：
- stdout 只输出最终文件路径（或为空）
- 所有日志和错误信息输出到 stderr
- 错误格式：`ERROR: {message}\nHINT: {hint}`

### 7. 注册全局命令

**修改文件**：`/Users/trouva/CODE/PYTHON/PyBits/pyproject.toml`

**修改内容**：
```toml
[project.scripts]
HELLO = "HELLO.cli:main"
SKILLS = "SKILLS.src.cli:main"
PTM = "PTM.cli:main"  # 新增

[tool.setuptools.packages.find]
include = ["HELLO*", "SKILLS*", "PTM*"]  # 新增 PTM*
```

**安装命令**：
```bash
cd /Users/trouva/CODE/PYTHON/PyBits
uv pip install -e .
```

### 8. 编写文档（PTM/README.md）

**内容**：
- 项目简介
- 安装方法
- API Token 获取（https://mineru.net）
- 使用示例
- CLI 参数说明
- 错误排查
- 限制说明（200MB，600 页）

## 关键文件路径

**需要创建的文件**：
- `/Users/trouva/CODE/PYTHON/PyBits/PTM/README.md`
- `/Users/trouva/CODE/PYTHON/PyBits/PTM/cli.py`
- `/Users/trouva/CODE/PYTHON/PyBits/PTM/src/__init__.py`
- `/Users/trouva/CODE/PYTHON/PyBits/PTM/src/constants.py`
- `/Users/trouva/CODE/PYTHON/PyBits/PTM/src/models.py`
- `/Users/trouva/CODE/PYTHON/PyBits/PTM/src/config.py`
- `/Users/trouva/CODE/PYTHON/PyBits/PTM/src/pdf_validator.py`
- `/Users/trouva/CODE/PYTHON/PyBits/PTM/src/api_client.py`
- `/Users/trouva/CODE/PYTHON/PyBits/PTM/src/file_handler.py`

**需要修改的文件**：
- `/Users/trouva/CODE/PYTHON/PyBits/pyproject.toml`

## CLI 参数完整列表

```bash
PTM input.pdf [OPTIONS]

必填参数:
  input_pdf              输入 PDF 文件路径

可选参数:
  --out-dir DIR          输出目录（默认：输入文件同目录）
  --token TOKEN          MinerU API token
  --timeout SECONDS      总超时时间（默认：300）
  --poll-interval SEC    轮询间隔（默认：3）
  --model-version VER    模型版本：pipeline/vlm/MinerU-HTML（默认：vlm）
  --lang LANG            语言代码（默认：ch）
  --images               保留图片到 imgs/ 目录
  --ocr                  启用 OCR
  --table                启用表格识别（默认启用）
  --no-table             禁用表格识别
  --formula              启用公式识别（默认启用）
  --no-formula           禁用公式识别
  --page-ranges RANGES   页码范围（例如："2,4-6"）
  --proxy URL            HTTP 代理 URL
  --keep-zip             保留下载的 zip 文件
  -h, --help             显示帮助信息
```
### 9. 测试验证

使用 `_shared/tests/` 下的脚本验证项目结构和全局命令：

```bash
cd /Users/trouva/CODE/PYTHON/PyBits

# 1. 基础信息检查
python _shared/tests/basic_info_check.py PTM
# 检查项：
# - 目录名是否为 UPPER-KEBAB-CASE
# - 是否存在 README.md, cli.py, src/ 目录
# - Python 文件是否使用 snake_case 命名
# - 非标准目录是否使用 _ 前缀

# 2. 全局命令检查
python _shared/tests/global_command_check.py PTM
# 检查项：
# - pyproject.toml 中是否注册了 PTM 命令
# - 命令是否可执行
# - --help 参数是否正常工作
# - 无效参数是否返回非零退出码
```

**如果测试不通过**：
- 检查目录结构是否符合规范
- 检查 `pyproject.toml` 中的 `[project.scripts]` 和 `[tool.setuptools.packages.find]`
- 重新安装：`uv pip install -e .`
- 查看测试脚本的具体错误信息并修复

#### 9.3 验证清单

**输出验证**：
- [ ] stdout 只输出最终文件路径（成功时）或为空（失败时）
- [ ] stderr 包含日志信息（INFO/ERROR 级别）
- [ ] 输出文件命名正确：`{input}_PTM_YYYYMMDD_HHMMSS.md`
- [ ] Markdown 内容完整可读
- [ ] 启用 `--images` 时，`imgs/` 目录存在且包含图片
- [ ] 启用 `--keep-zip` 时，zip 文件被保留
- [ ] 未启用 `--keep-zip` 时，zip 文件被删除

**错误处理验证**：
- [ ] 所有错误都输出 `ERROR: xxx` 格式
- [ ] 所有错误都有对应的 `HINT: xxx` 提示
- [ ] 日志中不包含完整 Token（已脱敏）
- [ ] 失败时退出码为 1，成功时为 0

**性能验证**：
- [ ] 小文件（< 5MB）转换时间 < 60 秒
- [ ] 进度条正常显示（上传、轮询、下载）
- [ ] 轮询间隔符合 `--poll-interval` 设置

## 错误处理矩阵

| 错误场景 | ERROR 信息 | HINT 信息 |
|---------|-----------|----------|
| 文件不存在 | `File not found: {path}` | `Check the file path and try again` |
| 非 PDF 文件 | `Not a valid PDF file: {path}` | `Provide a file with .pdf extension and valid PDF format` |
| 文件过大 | `File too large: {size}MB (max 200MB)` | `Split the PDF or compress it` |
| 页数超限 | `Too many pages: ~{count} pages (max 600)` | `Split the PDF or use --page-ranges` |
| 无 Token | `No API token provided` | `Provide token via --token, MINERU_API_TOKEN env var, or PTM/.env file` |
| Token 无效 | `Invalid or expired token` | `Get a new token from https://mineru.net` |
| 上传失败 | `Upload failed: HTTP {code}` | `Check network connection and try again` |
| 超时 | `Timeout after {timeout} seconds` | `Try increasing --timeout or check PDF complexity` |
| API 失败 | `API processing failed: {message}` | `Check PDF format and try again` |
| imgs/ 已存在 | `imgs/ directory already exists: {path}` | `Remove it or disable --images` |


## 实现顺序

1. **基础结构**：创建目录和空文件
2. **常量和模型**：`constants.py`, `models.py`
3. **配置管理**：`config.py`（Token 加载）
4. **PDF 校验**：`pdf_validator.py`
5. **API 客户端**：`api_client.py`（核心逻辑）
6. **文件处理**：`file_handler.py`
7. **CLI 入口**：`cli.py`（整合所有模块）
8. **文档**：`README.md`
9. **注册命令**：修改 `pyproject.toml`
10. **测试验证**：运行测试命令

## 注意事项

1. **页数限制矛盾**：用户需求提到 200 页，但 MinerU API 实际限制是 600 页。实现时使用 API 的实际限制（600 页），并在文档中说明。

2. **Token 配置**：
   - 日志中使用 `mask_token()` 脱敏
   - 不打印签名 URL（包含临时凭证）
   - 推荐使用 `PTM/.env` 文件存储 Token（方便且安全，只要确保 `.gitignore` 包含 `.env`）

3. **错误处理**：
   - 所有 `PTMError` 必须包含 `message` 和 `hint`
   - 其他异常记录完整堆栈到日志

4. **输出规范**：
   - stdout：只输出最终文件路径（成功时）或为空（失败时）
   - stderr：所有日志和错误信息
   - 退出码：0（成功）或 1（失败）

5. **依赖管理**：
   - 不需要新增依赖
   - 所有功能使用现有依赖和标准库实现

6. **项目规范**：
   - 目录名：`PTM`（UPPER-KEBAB-CASE）
   - Python 文件：`snake_case.py`
   - 必须文件：`README.md`, `cli.py`, `src/`
   - 全局命令：`PTM = "PTM.cli:main"`
