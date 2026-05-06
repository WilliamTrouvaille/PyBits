#!/usr/bin/env python3
"""ArXiv to Prompt - 下载并转换 arXiv 论文的 LaTeX 源码。

用法:
    ATP <arxiv-id-or-url>                    # 输出到桌面
    ATP <arxiv-id-or-url> --out-dir <dir>    # 自定义输出目录
    ATP <arxiv-id-or-url> --json             # 输出 manifest.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import NoReturn

from loguru import logger
from rich.console import Console

console = Console()
console_err = Console(stderr=True)

# 项目根目录和缓存目录
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
CACHE_ROOT = SCRIPT_DIR / ".paper"
LOG_DIR = SCRIPT_DIR / "logs"


def extract_arxiv_id(raw: str) -> tuple[str, bool]:
    """提取 arXiv ID，保留版本号。

    Args:
        raw: 用户输入的字符串（ID 或 URL）

    Returns:
        (arxiv_id, has_version): ID 和是否包含版本号

    Raises:
        ValueError: 无法识别的输入格式
    """
    raw = raw.strip()

    # 裸 ID：1911.11763 或 1911.11763v2
    m = re.match(r"^(\d{4}\.\d{4,5})(v\d+)?$", raw)
    if m:
        arxiv_id = m.group(1) + (m.group(2) or "")
        has_version = m.group(2) is not None
        return arxiv_id, has_version

    # URL：https://arxiv.org/abs/1911.11763v2 或 .../pdf/...
    m = re.match(r"https?://arxiv\.org/(abs|pdf)/(\d{4}\.\d{4,5})(v\d+)?", raw)
    if m:
        arxiv_id = m.group(2) + (m.group(3) or "")
        has_version = m.group(3) is not None
        return arxiv_id, has_version

    raise ValueError(f"无法识别的 arXiv ID 或 URL: {raw}")


def get_desktop_path() -> Path:
    """获取系统桌面路径（跨平台）。

    Returns:
        桌面路径
    """
    if sys.platform == "win32":
        # Windows
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        )
        desktop = winreg.QueryValueEx(key, "Desktop")[0]
        winreg.CloseKey(key)
        return Path(desktop)
    else:
        # macOS / Linux
        return Path.home() / "Desktop"


def check_arxiv_tool() -> bool:
    """检查 arxiv-to-prompt 是否已安装。

    Returns:
        True 如果已安装，False 否则
    """
    try:
        result = subprocess.run(
            ["arxiv-to-prompt", "--help"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_cache(arxiv_id: str) -> Path | None:
    """检查缓存是否存在。

    Args:
        arxiv_id: arXiv ID

    Returns:
        缓存的 .tex 文件路径，如果不存在则返回 None
    """
    cache_dir = CACHE_ROOT / arxiv_id
    if not cache_dir.exists():
        return None

    # 查找 .tex 文件
    tex_files = list(cache_dir.glob("*.tex"))
    if not tex_files:
        tex_files = list(cache_dir.rglob("*.tex"))

    if tex_files:
        # 返回最大的 .tex 文件
        main_tex = max(tex_files, key=lambda f: f.stat().st_size)
        if main_tex.stat().st_size > 0:
            return main_tex

    return None


def download_paper(
    arxiv_id: str,
    cache_dir: Path,
    proxy: str | None,
    no_comments: bool,
    no_appendix: bool,
    timeout: int = 90,
) -> Path:
    """下载并转换论文。

    Args:
        arxiv_id: arXiv ID
        cache_dir: 缓存目录
        proxy: 代理 URL
        no_comments: 是否移除注释
        no_appendix: 是否移除附录
        timeout: 超时时间（秒）

    Returns:
        转换后的 .tex 文件路径

    Raises:
        RuntimeError: 下载或转换失败
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 构建命令
    cmd = [
        "arxiv-to-prompt",
        arxiv_id,
        "--force-download",
        "--cache-dir",
        str(cache_dir),
    ]
    if no_comments:
        cmd.append("--no-comments")
    if no_appendix:
        cmd.append("--no-appendix")

    # 设置环境变量（代理）
    env = os.environ.copy()
    if proxy:
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
        logger.info(f"使用代理: {proxy}")

    # 执行命令（带重试）
    logger.info(f"开始下载论文: {arxiv_id}")
    console.print("[cyan]正在拉取 arXiv TEX 包...[/cyan]")

    last_error = None
    for attempt in range(3):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

            # 记录 arxiv-to-prompt 的输出
            if result.stdout:
                logger.debug(f"arxiv-to-prompt stdout: {result.stdout}")
            if result.stderr:
                logger.debug(f"arxiv-to-prompt stderr: {result.stderr}")

            if result.returncode == 0:
                logger.info(f"下载成功，耗时约 {timeout} 秒内")
                break

            last_error = result.stderr
            logger.warning(f"下载失败 (尝试 {attempt + 1}/3): {result.stderr}")

        except subprocess.TimeoutExpired as exc:
            last_error = "网络超时"
            if attempt < 2:
                console.print(f"[yellow]网络超时，正在重试 ({attempt + 1}/3)...[/yellow]")
                logger.warning(f"网络超时，正在重试 ({attempt + 1}/3)")
                time.sleep(5)
            else:
                logger.error("下载超时，已重试 3 次")
                raise RuntimeError("下载超时，已重试 3 次") from exc
    else:
        # 所有重试都失败
        raise RuntimeError(f"arxiv-to-prompt 执行失败: {last_error}")

    # 查找生成的 .tex 文件
    console.print("[cyan]正在本地处理...[/cyan]")
    tex_files = list(cache_dir.glob("*.tex"))
    if not tex_files:
        tex_files = list(cache_dir.rglob("*.tex"))

    if not tex_files:
        logger.error(f"未找到生成的 .tex 文件，缓存目录: {cache_dir}")
        raise RuntimeError("未找到生成的 .tex 文件")

    main_tex = max(tex_files, key=lambda f: f.stat().st_size)
    logger.info(f"找到主 .tex 文件: {main_tex} ({main_tex.stat().st_size} 字节)")
    return main_tex


def extract_figures(
    arxiv_id: str,
    cache_dir: Path,
    output_dir: Path,
    no_comments: bool,
    no_appendix: bool,
) -> list[Path]:
    """提取图片路径并并发复制到输出目录。

    Args:
        arxiv_id: arXiv ID
        cache_dir: 缓存目录
        output_dir: 输出目录
        no_comments: 是否移除注释
        no_appendix: 是否移除附录

    Returns:
        复制后的图片路径列表
    """
    # 调用 arxiv-to-prompt --figure-paths 获取图片路径
    cmd = [
        "arxiv-to-prompt",
        arxiv_id,
        "--figure-paths",
        "--cache-dir",
        str(cache_dir),
    ]
    if no_comments:
        cmd.append("--no-comments")
    if no_appendix:
        cmd.append("--no-appendix")

    logger.info("开始提取图片路径")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        logger.warning(f"图片提取失败: {result.stderr}")
        return []

    # 解析图片路径（每行一个路径）
    figure_paths = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]

    if not figure_paths:
        logger.info("未找到图片")
        return []

    logger.info(f"找到 {len(figure_paths)} 张图片")

    # 创建输出目录
    figure_output_dir = output_dir / "figure"
    figure_output_dir.mkdir(parents=True, exist_ok=True)

    # 并发复制图片
    def copy_figure(src: Path) -> Path:
        dst = figure_output_dir / src.name
        shutil.copy2(src, dst)
        logger.debug(f"复制图片: {src.name} -> {dst}")
        return dst

    console.print(f"[cyan]正在复制 {len(figure_paths)} 张图片...[/cyan]")
    with ThreadPoolExecutor(max_workers=4) as executor:
        copied_paths = list(executor.map(copy_figure, figure_paths))

    logger.info(f"图片复制完成: {len(copied_paths)} 张")
    return copied_paths


def generate_manifest(
    arxiv_id: str,
    tex_path: Path,
    figure_paths: list[Path] | None,
) -> dict:
    """生成 manifest.json。

    Args:
        arxiv_id: arXiv ID
        tex_path: .tex 文件路径
        figure_paths: 图片路径列表（可选）

    Returns:
        manifest 字典
    """
    source_url = f"https://arxiv.org/abs/{arxiv_id}"

    manifest = {
        "arxiv_id": arxiv_id,
        "source_url": source_url,
        "raw_tex_path": str(tex_path.resolve()),
    }

    if figure_paths is not None:
        manifest["figure_paths"] = [str(p.resolve()) for p in figure_paths]

    return manifest


def setup_logger(log_dir: Path, json_mode: bool = False) -> None:
    """配置日志系统。

    Args:
        log_dir: 日志目录
        json_mode: 是否为 JSON 模式（日志输出到 stderr）
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    # 清理过期日志（保留 30 天）
    cutoff = datetime.now() - timedelta(days=30)
    for log_file in log_dir.glob("*.log"):
        try:
            if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff:
                log_file.unlink()
        except Exception:
            pass

    # 移除默认 handler
    logger.remove()

    # 配置文件日志
    log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} [{level}] {message}",
        level="DEBUG",
        encoding="utf-8",
    )

    # 配置控制台日志（JSON 模式下输出到 stderr）
    if json_mode:
        logger.add(
            sys.stderr,
            format="{time:YYYY-MM-DD HH:mm:ss} [{level}] {message}",
            level="INFO",
        )


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns:
        ArgumentParser 实例
    """
    parser = argparse.ArgumentParser(
        prog="ATP",
        description="下载并转换 arXiv 论文的 LaTeX 源码",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  ATP 1911.11763                           # 输出到桌面
  ATP https://arxiv.org/abs/2303.08774     # 使用 URL
  ATP 1911.11763 --out-dir ./papers        # 自定义输出目录
  ATP 1911.11763 --json                    # 输出 manifest.json
  ATP 1911.11763 --force                   # 强制重新下载
  ATP 1911.11763 --proxy http://proxy:8080 # 使用代理
        """,
    )

    parser.add_argument(
        "arxiv_input",
        metavar="<arxiv-id-or-url>",
        help="arXiv ID 或 URL（如 1911.11763 或 https://arxiv.org/abs/1911.11763）",
    )

    parser.add_argument(
        "--out-dir",
        type=Path,
        help="输出目录（默认：系统桌面）",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 manifest.json 到 --out-dir 并打印到 stdout",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新下载，忽略缓存",
    )

    parser.add_argument(
        "--proxy",
        type=str,
        help="代理 URL（如 http://proxy:8080）",
    )

    parser.add_argument(
        "--no-comments",
        action="store_true",
        default=True,
        help="移除注释（默认启用）",
    )

    parser.add_argument(
        "--comments",
        action="store_true",
        help="保留注释（覆盖 --no-comments）",
    )

    parser.add_argument(
        "--figure-paths",
        action="store_true",
        default=True,
        help="提取图片并复制（默认启用）",
    )

    parser.add_argument(
        "--no-figure-paths",
        action="store_true",
        help="不提取图片（覆盖 --figure-paths）",
    )

    parser.add_argument(
        "--no-appendix",
        action="store_true",
        help="移除附录",
    )

    return parser


def error_exit(message: str, exit_code: int = 1) -> NoReturn:
    """输出错误信息并退出。

    Args:
        message: 错误信息
        exit_code: 退出码
    """
    console_err.print(f"[red]错误: {message}[/red]")
    logger.error(message)
    sys.exit(exit_code)


def main() -> int:
    """主入口函数。

    Returns:
        退出码（0 表示成功）
    """
    parser = build_parser()
    args = parser.parse_args()

    # 配置日志
    setup_logger(LOG_DIR, json_mode=args.json)

    # 记录用户输入
    logger.info(f"用户输入: {args.arxiv_input}")
    logger.info(f"命令行参数: {sys.argv[1:]}")

    # 检查 arxiv-to-prompt 是否已安装
    if not check_arxiv_tool():
        error_exit("未找到 arxiv-to-prompt 工具\n请先安装: uv tool install arxiv-to-prompt")

    # 提取 arXiv ID
    try:
        arxiv_id, has_version = extract_arxiv_id(args.arxiv_input)
        logger.info(
            f"解析得到 arXiv ID: {arxiv_id} ({'包含版本号' if has_version else '无版本号'})"
        )
    except ValueError as e:
        error_exit(str(e))

    # 确定输出目录
    output_dir = args.out_dir.resolve() if args.out_dir else get_desktop_path()
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"输出目录: {output_dir}")

    # 处理参数覆盖
    no_comments = args.no_comments and not args.comments
    extract_figures_flag = args.figure_paths and not args.no_figure_paths

    # 记录省略参数补全
    logger.info(
        f"参数补全: --out-dir={output_dir}, "
        f"--no-comments={no_comments}, "
        f"--figure-paths={extract_figures_flag}, "
        f"--no-appendix={args.no_appendix}"
    )

    # 检查缓存
    cache_dir = CACHE_ROOT / arxiv_id
    cached_tex = None if args.force else check_cache(arxiv_id)

    if cached_tex and not args.force:
        logger.info(f"缓存命中: {cached_tex}")
        console.print(f"[green]使用缓存: {arxiv_id}[/green]")
        tex_path = cached_tex
    else:
        if args.force:
            logger.info("忽略缓存，强制重新下载")
        else:
            logger.info(f"缓存未命中: {cache_dir}")

        # 下载论文
        try:
            tex_path = download_paper(
                arxiv_id,
                cache_dir,
                args.proxy,
                no_comments,
                args.no_appendix,
            )
        except Exception as e:
            error_exit(f"下载失败: {e}")

    # 复制 .tex 文件到输出目录
    output_tex = output_dir / f"{arxiv_id}.tex"
    shutil.copy2(tex_path, output_tex)
    logger.info(f"写入文件: {output_tex}")
    console.print(f"[green]OK[/green] TEX 文件: {output_tex}")

    # 提取图片
    figure_paths = None
    if extract_figures_flag:
        try:
            figure_paths = extract_figures(
                arxiv_id,
                cache_dir,
                output_dir,
                no_comments,
                args.no_appendix,
            )
            if figure_paths:
                console.print(
                    f"[green]OK[/green] 图片: {len(figure_paths)} 张 -> {output_dir / 'figure'}"
                )
        except Exception as e:
            logger.warning(f"图片提取失败: {e}")
            console.print(f"[yellow]警告: 图片提取失败: {e}[/yellow]")

    # 生成 manifest.json
    if args.json:
        manifest = generate_manifest(arxiv_id, output_tex, figure_paths)
        manifest_path = output_dir / "manifest.json"

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        logger.info(f"写入 manifest: {manifest_path}")

        # 输出到 stdout
        print(json.dumps(manifest, ensure_ascii=False, indent=2))

    logger.info("执行成功，退出码 0")
    console.print("[green]完成[/green]")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        console_err.print("\n[yellow]操作已取消[/yellow]")
        logger.warning("用户中断操作")
        sys.exit(130)
    except Exception as e:
        console_err.print(f"[red]未预期的错误: {e}[/red]")
        logger.exception("未预期的错误")
        sys.exit(1)
