# ATP - ArXiv to Prompt

将 arXiv 论文转换为可读的 LaTeX 源码，方便阅读和分析。

## 功能特性

- 📥 自动下载 arXiv 论文的 LaTeX 源码
- 📝 支持移除注释和附录，提高可读性
- 🖼️ 自动提取并复制论文图片
- 💾 智能缓存机制，避免重复下载
- 🌐 支持代理配置
- 📊 可选 JSON manifest 输出

## 安装

### 1. 安装依赖

本工具依赖 `arxiv-to-prompt`，需要先安装：

```bash
uv tool install arxiv-to-prompt
```

### 2. 验证安装

```bash
arxiv-to-prompt --help
```

## 使用方法

### 基本用法

**默认命令**（输出到桌面）：

```bash
ATP 1911.11763
ATP https://arxiv.org/abs/2303.08774
```

这会：

- 下载论文并转换为 `.tex` 文件，保存到桌面
- 提取图片到桌面的 `figure/` 文件夹
- 自动移除注释（`--no-comments`）
- 自动提取图片（`--figure-paths`）

### 自定义输出目录

```bash
ATP 1911.11763 --out-dir ./papers
```

### 输出 JSON manifest

```bash
ATP 1911.11763 --json
```

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

- 不带 `--json`：只写 `.tex` 文件，日志输出到 stderr
- 带 `--json`：写入 `manifest.json` 到 `--out-dir`，同时 stdout 输出 JSON，日志走 stderr

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

| 参数                | 说明                    | 默认值         |
| ------------------- | ----------------------- | -------------- |
| `<arxiv-id-or-url>` | arXiv ID 或 URL（必需） | -              |
| `--out-dir <path>`  | 输出目录                | 系统桌面       |
| `--json`            | 输出 manifest.json      | 否             |
| `--force`           | 强制重新下载            | 否             |
| `--proxy <url>`     | 代理 URL                | 无             |
| `--no-comments`     | 移除注释                | 是（默认启用） |
| `--comments`        | 保留注释                | 否             |
| `--figure-paths`    | 提取图片                | 是（默认启用） |
| `--no-figure-paths` | 不提取图片              | 否             |
| `--no-appendix`     | 移除附录                | 否             |
| `-h, --help`        | 显示帮助                | -              |

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

ATP 会将下载的论文缓存到 `./ATP/.paper/<arxiv_id>/`，避免重复下载。

**缓存策略**：

- 默认检查缓存：如果存在有效的 `.tex` 文件，直接复用
- 使用 `--force` 参数：忽略缓存，强制重新下载

## 日志

日志文件保存在 `./ATP/logs/`，按日期分文件（如 `2026-05-07.log`）。

**日志内容**：

- 用户输入和命令行参数
- arXiv ID 提取结果
- 缓存检查状态
- 下载进度和耗时
- 文件写入路径
- 错误堆栈

**日志保留**：自动清理 30 天前的日志。

## 错误处理

- **网络超时**：自动重试 3 次，间隔 5 秒
- **404 / 解析错误**：不重试，直接失败
- **超时时间**：90 秒
- **退出码**：成功为 0，失败为非 0

## 性能优化

- **并发复制图片**：使用 4 个线程并发复制图片，提升速度
- **智能缓存**：避免重复下载，节省时间和带宽

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

### 示例 3：生成 JSON 用于自动化

```bash
# 输出 JSON manifest，方便脚本处理
ATP 1911.11763 --json > paper_info.json
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
3. 查看日志文件：`./ATP/logs/YYYY-MM-DD.log`

## 未来规划

以下功能计划在未来版本中实现：

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

6. **解耦代码**：将`ATP\atp.py`解耦到`ATP\src\`文件夹下

## 技术细节

- **上游项目**：[arxiv-to-prompt](https://github.com/takashiishida/arxiv-to-prompt)
- **Python 版本**：>= 3.13
- **依赖**：`rich`, `loguru`（通过项目 `pyproject.toml` 管理）
- **缓存位置**：`./ATP/.paper/`
- **日志位置**：`./ATP/logs/`

## 许可证

本工具遵循项目根目录的许可证。

## 贡献

欢迎提交 Issue 和 Pull Request！
