# ATP - ArXiv to Prompt

将 arXiv 论文转换为可读的 LaTeX 源码，方便阅读和分析。

## 功能特性

- 调用外部 `arxiv-to-prompt` 命令下载并转换 arXiv LaTeX 源码。
- 默认移除注释、提取图片路径并复制图片到输出目录。
- 支持保留注释、移除附录、强制重新下载和代理参数。
- 使用本地缓存避免重复下载；缓存命中时直接复制缓存中的 `.tex` 文件。
- 可选写入 `manifest.json`，记录论文 ID、来源 URL、输出 TEX 路径和图片路径。

## 安装与依赖

ATP 是 PyBits 的一个全局命令，入口在项目根 `pyproject.toml` 的 `[project.scripts]` 中注册为 `ATP = "ATP.cli:main"`。

项目内 Python 依赖由根目录 `pyproject.toml` 统一管理，当前要求 Python `>=3.12`。ATP 自身还会通过 `subprocess` 调用外部命令 `arxiv-to-prompt`，因此需要确保该命令已安装且在 `PATH` 中：

```bash
uv tool install arxiv-to-prompt
```

验证外部命令：

```bash
arxiv-to-prompt --help
```

## 使用方法

### 基本用法

默认输出到系统桌面：

```bash
ATP 1911.11763
ATP https://arxiv.org/abs/2303.08774
```

这会：

- 下载论文并转换为 `.tex` 文件，保存到桌面
- 默认移除注释（等价于启用 `--no-comments`）
- 默认提取图片路径并复制图片到桌面的 `figure/` 文件夹

### 自定义输出目录

```bash
ATP 1911.11763 --out-dir ./papers
```

### 写入 JSON manifest

```bash
ATP 1911.11763 --json
```

带 `--json` 时，ATP 会将 `manifest.json` 写入 `--out-dir`，并在标准输出中打印同一份 JSON 对象。状态信息、警告和进度提示会输出到 stderr，因此 stdout 可作为机器可读 JSON 使用。

生成的 `manifest.json` 格式：

```json
{
  "arxiv_id": "1911.11763v2",
  "source_url": "https://arxiv.org/abs/1911.11763v2",
  "raw_tex_path": "D:/abs/path/1911.11763v2.tex",
  "figure_paths": ["D:/abs/path/figure/001.jpg", "D:/abs/path/figure/002.jpg"]
}
```

**注意**：

- 不带 `--json`：只写 `.tex` 文件；日志走 stderr，状态信息会打印到 stdout。
- 带 `--json`：写入 `manifest.json` 到 `--out-dir`，stdout 只输出 JSON 对象，状态信息走 stderr。
- 使用 `--no-figure-paths` 时不会提取图片，manifest 中也不会包含 `figure_paths` 字段。

### 强制重新下载

```bash
ATP 1911.11763 --force
```

忽略缓存，强制重新下载论文。

### 使用代理

```bash
ATP 1911.11763 --proxy http://proxy.example.com:8080
```

### 保留注释

```bash
ATP 1911.11763 --comments
```

默认会移除注释，使用 `--comments` 保留。

### 不提取图片

```bash
ATP 1911.11763 --no-figure-paths
```

默认会提取图片，使用 `--no-figure-paths` 跳过。

### 移除附录

```bash
ATP 1911.11763 --no-appendix
```

### 组合使用

```bash
ATP 1911.11763 --out-dir ./papers --json --no-appendix --force
```

## 命令行参数

| 参数                | 说明                                      | 默认行为 |
| ------------------- | ----------------------------------------- | -------- |
| `<arxiv-id-or-url>` | arXiv ID 或 URL（必需）                   | -        |
| `--out-dir <path>`  | 输出目录                                  | 系统桌面 |
| `--json`            | 写入 `manifest.json` 并在 stdout 打印 JSON 对象 | 否       |
| `--force`           | 忽略缓存，强制重新下载                    | 否       |
| `--proxy <url>`     | 为主下载和图片提取阶段设置 `HTTP_PROXY` / `HTTPS_PROXY` | 无       |
| `--no-comments`     | 移除注释                                  | 是       |
| `--comments`        | 保留注释，覆盖默认的 `--no-comments`      | 否       |
| `--figure-paths`    | 提取图片路径并复制图片                    | 是       |
| `--no-figure-paths` | 跳过图片提取，覆盖默认的 `--figure-paths` | 否       |
| `--no-appendix`     | 移除附录                                  | 否       |
| `-h, --help`        | 显示帮助                                  | -        |

## 版本号支持

ATP 支持带版本号的 arXiv ID：

```bash
# 不带版本号（使用最新版本）
ATP 1911.11763

# 带版本号（使用指定版本）
ATP 1911.11763v2
```

**行为**：

- 如果输入带版本号，`arxiv_id` 和 `source_url` 都保留版本号
- 如果输入不带版本号，`arxiv_id` 和 `source_url` 都不主动追加版本号

## 缓存机制

ATP 的缓存根目录由代码中的工具包路径决定：

- 在源码目录通过 `uv run ATP ...` 运行时，缓存位于 `ATP/.paper/<arxiv_id>/`。
- 通过全局命令运行时，缓存仍以已安装的 ATP 包目录为基准，不以当前工作目录为基准。

**缓存策略**：

- 默认检查缓存：如果缓存目录中存在非空 `.tex` 文件，直接复用；当存在多个 `.tex` 文件时，选择文件大小最大的一个
- 使用 `--force` 参数：忽略缓存，强制重新下载

## 日志

日志使用 PyBits 共享日志工具：

- 源码或安装来源目录可写时，日志保存在 `ATP/logs/`。
- 日志文件按工具名和日期命名，例如 `atp_2026-05-07.log`。
- 如果安装来源日志目录不可写，会回退到 ATP 包目录下的 `logs/`。
- 30 天前的旧日志会通过 PyBits 软删除机制移动到 `.codex/_trash_bin_/`。

**日志内容**：

- 用户输入和命令行参数
- arXiv ID 提取结果
- 缓存检查状态
- 下载进度和耗时
- 文件写入路径
- 错误堆栈

## 错误处理

- **缺少外部命令**：启动工作流后先检查 `arxiv-to-prompt --help`，找不到时直接失败。
- **输入格式错误**：支持裸 ID、带版本号 ID、`/abs/` URL 和 `/pdf/` URL；无法识别时失败。
- **主下载超时**：单次超时时间为 90 秒，最多尝试 3 次，超时重试间隔 5 秒。
- **外部命令非 0 退出**：当前实现最多尝试 3 次，没有对 404 或解析错误做特殊分流。
- **图片提取失败**：记录 warning 并继续完成 TEX 输出；图片路径为空。
- **退出码**：成功为 0，失败为非 0。

## 性能优化

- **并发复制图片**：使用 4 个线程并发复制图片。
- **本地缓存**：缓存命中时跳过主下载流程。

## 示例

### 示例 1：快速阅读论文

```bash
# 下载到桌面，自动移除注释和提取图片
ATP 1911.11763
```

### 示例 2：保存到项目目录

```bash
# 保存到项目的 papers 目录
ATP 2303.08774 --out-dir ./papers
```

### 示例 3：写入 JSON manifest

```bash
# 生成 ./papers/manifest.json，并可将 stdout 重定向为纯 JSON
ATP 1911.11763 --out-dir ./papers --json > paper_info.json
```

### 示例 4：使用代理下载

```bash
# 通过代理下载
ATP 1911.11763 --proxy http://127.0.0.1:7890
```

### 示例 5：完整控制

```bash
# 自定义所有参数
ATP 1911.11763v2 \
  --out-dir ./research/papers \
  --json \
  --no-appendix \
  --force \
  --proxy http://proxy:8080
```

## 故障排除

### 问题：提示 "未找到 arxiv-to-prompt 工具"

**解决方案**：

```bash
uv tool install arxiv-to-prompt
```

### 问题：下载超时

**解决方案**：

1. 检查网络连接
2. 使用代理：`ATP <id> --proxy http://proxy:8080`
3. 使用 `--force` 重试：`ATP <id> --force`

### 问题：无法识别 arXiv ID

**解决方案**：

确保输入格式正确：

- 裸 ID：`1911.11763` 或 `1911.11763v2`
- URL：`https://arxiv.org/abs/1911.11763` 或 `https://arxiv.org/pdf/1911.11763.pdf`

### 问题：图片提取失败

**解决方案**：

1. 检查论文是否包含图片
2. 使用 `--force` 重新下载：`ATP <id> --force`
3. 查看日志文件：`./ATP/logs/atp_YYYY-MM-DD.log`

## 未来规划

以下功能尚未在当前参数解析器中实现，属于未来规划：

1. **批量处理**：支持一次处理多个 arXiv ID

   ```bash
   ATP 1911.11763 2303.08774 2301.98765
   ```

2. **Zotero 集成**：从 Zotero 库导入论文

   ```bash
   ATP --from-zotero "Machine Learning"
   ```

3. **缓存校验**：使用 SHA256 校验缓存完整性

   ```bash
   ATP 1911.11763 --verify-cache
   ```

4. **配置文件**：支持 `ATP/config.toml` 设置默认行为

   ```toml
   [default]
   output_dir = "~/papers"
   proxy = "http://proxy:8080"
   no_comments = true
   ```

5. **进度条优化**：使用 rich 的 Progress 显示下载进度

6. **图片提取错误细分**：区分论文无图片、上游输出变化和网络失败

## 技术细节

- **上游项目**：[arxiv-to-prompt](https://github.com/takashiishida/arxiv-to-prompt)
- **入口点**：`ATP.cli:main`
- **Python 版本**：项目声明 `>=3.12`
- **项目依赖**：`rich`, `loguru` 等由根目录 `pyproject.toml` 统一管理
- **外部命令依赖**：`arxiv-to-prompt`
- **缓存位置**：源码运行时为 `ATP/.paper/`
- **日志位置**：通常为 `ATP/logs/`，日志文件名形如 `atp_YYYY-MM-DD.log`

## 许可证

本工具遵循项目根目录的许可证。

## 贡献

欢迎提交 Issue 和 Pull Request！
