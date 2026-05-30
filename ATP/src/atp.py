#!/usr/bin/env python3
"""ArXiv to Prompt - 下载并转换 arXiv 论文的 LaTeX 源码。

用法:
    ATP <arxiv-id-or-url>                    # 输出到桌面
    ATP <arxiv-id-or-url> --out-dir <dir>    # 自定义输出目录
    ATP <arxiv-id-or-url> --json             # 输出 manifest.json
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NoReturn

from loguru import logger
from rich.console import Console

from _shared.utils.logging import setup_tool_logger

from .cli_parser import build_parser

console = Console()
console_err = Console(stderr=True)

# 工具根目录和缓存目录
TOOL_ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = TOOL_ROOT / ".paper"
LOG_DIR = TOOL_ROOT / "logs"


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

    # 支持 arxiv.org/abs/... 与 arxiv.org/pdf/... URL，并保留可选版本号。
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


def find_main_tex_file(cache_dir: Path) -> Path | None:
    """
    在缓存目录中查找最可能的主 .tex 文件。

    Args:
        cache_dir: arxiv-to-prompt 的缓存目录。

    Returns:
        文件大小最大的非空 .tex 文件；找不到时返回 None。
    """
    tex_files = list(cache_dir.glob("*.tex"))
    if not tex_files:
        tex_files = list(cache_dir.rglob("*.tex"))

    if not tex_files:
        return None

    main_tex = max(tex_files, key=lambda f: f.stat().st_size)
    if main_tex.stat().st_size > 0:
        return main_tex
    return None


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

    return find_main_tex_file(cache_dir)


def build_arxiv_to_prompt_command(
    arxiv_id: str,
    cache_dir: Path,
    no_comments: bool,
    no_appendix: bool,
    *,
    figure_paths: bool = False,
) -> list[str]:
    """
    构建 arxiv-to-prompt 命令参数。

    Args:
        arxiv_id: arXiv ID。
        cache_dir: 缓存目录。
        no_comments: 是否移除注释。
        no_appendix: 是否移除附录。
        figure_paths: 是否请求输出图片路径。

    Returns:
        可直接传给 subprocess.run 的命令列表。
    """
    cmd = ["arxiv-to-prompt", arxiv_id]
    if figure_paths:
        cmd.append("--figure-paths")
    else:
        cmd.append("--force-download")
    cmd.extend(["--cache-dir", str(cache_dir)])
    if no_comments:
        cmd.append("--no-comments")
    if no_appendix:
        cmd.append("--no-appendix")
    return cmd


def build_proxy_env(proxy: str | None) -> dict[str, str] | None:
    """
    根据代理参数构建子进程环境变量。

    Args:
        proxy: HTTP(S) 代理 URL。

    Returns:
        设置了代理的环境变量副本；未提供代理时返回 None。
    """
    if not proxy:
        return None
    env = os.environ.copy()
    env["HTTP_PROXY"] = proxy
    env["HTTPS_PROXY"] = proxy
    logger.info(f"使用代理: {proxy}")
    return env


def download_paper(
    arxiv_id: str,
    cache_dir: Path,
    proxy: str | None,
    no_comments: bool,
    no_appendix: bool,
    timeout: int = 90,
) -> Path:
    """
    下载并转换论文。

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

    cmd = build_arxiv_to_prompt_command(
        arxiv_id,
        cache_dir,
        no_comments,
        no_appendix,
    )
    env = build_proxy_env(proxy)

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

    console.print("[cyan]正在本地处理...[/cyan]")
    main_tex = find_main_tex_file(cache_dir)
    if main_tex is None:
        logger.error(f"未找到生成的 .tex 文件，缓存目录: {cache_dir}")
        raise RuntimeError("未找到生成的 .tex 文件")

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
    cmd = build_arxiv_to_prompt_command(
        arxiv_id,
        cache_dir,
        no_comments,
        no_appendix,
        figure_paths=True,
    )

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
    setup_tool_logger(
        "atp",
        logs_dir=LOG_DIR,
        retention_days=30,
        console_level="INFO" if args.json else "WARNING",
    )

    # 记录用户输入
    logger.info(f"用户输入: {args.arxiv_input}")
    logger.info(f"命令行参数: {sys.argv[1:]}")

    return run_atp_workflow(args)


def run_atp_workflow(args: argparse.Namespace) -> int:
    """
    执行 ATP 的下载、复制、图片提取和 manifest 输出流程。

    Args:
        args: argparse 解析出的命名空间。

    Returns:
        进程退出码，0 表示处理成功。
    """
    if not check_arxiv_tool():
        error_exit("未找到 arxiv-to-prompt 工具\n请先安装: uv tool install arxiv-to-prompt")

    try:
        arxiv_id, has_version = extract_arxiv_id(args.arxiv_input)
        logger.info(
            f"解析得到 arXiv ID: {arxiv_id} ({'包含版本号' if has_version else '无版本号'})"
        )
    except ValueError as e:
        error_exit(str(e))

    output_dir = args.out_dir.resolve() if args.out_dir else get_desktop_path()
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"输出目录: {output_dir}")

    no_comments = args.no_comments and not args.comments
    extract_figures_flag = args.figure_paths and not args.no_figure_paths

    logger.info(
        f"参数补全: --out-dir={output_dir}, "
        f"--no-comments={no_comments}, "
        f"--figure-paths={extract_figures_flag}, "
        f"--no-appendix={args.no_appendix}"
    )

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

    output_tex = output_dir / f"{arxiv_id}.tex"
    shutil.copy2(tex_path, output_tex)
    logger.info(f"写入文件: {output_tex}")
    console.print(f"[green]OK[/green] TEX 文件: {output_tex}")

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

    if args.json:
        manifest = generate_manifest(arxiv_id, output_tex, figure_paths)
        manifest_path = output_dir / "manifest.json"

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        logger.info(f"写入 manifest: {manifest_path}")

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
