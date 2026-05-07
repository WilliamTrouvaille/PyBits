"""核心转换逻辑：模型检查下载、MinerU进程管理、超时控制、临时文件清理。"""

import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from loguru import logger
from rich.console import Console

console = Console(stderr=True)


def check_and_download_models(model_source: str, proxy: str | None) -> bool:
    """检查模型是否存在，不存在则下载。

    Args:
        model_source: 模型源（modelscope/huggingface）
        proxy: 代理地址

    Returns:
        是否成功
    """
    model_cache_dir = Path.home() / ".cache" / model_source / "hub"

    if model_cache_dir.exists() and any(model_cache_dir.iterdir()):
        logger.info(f"模型已存在: {model_cache_dir}")
        return True

    logger.info(f"模型不存在，开始下载到 {model_cache_dir}")

    cmd = ["magic-pdf", "--download-models", "--model-source", model_source]
    if proxy:
        cmd.extend(["--proxy", proxy])

    with console.status("[bold green]正在下载模型...", spinner="dots"):
        try:
            subprocess.run(cmd, capture_output=False, text=True, check=True)
            logger.info("模型下载完成")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"模型下载失败: {e}")
            return False
        except FileNotFoundError:
            logger.error("magic-pdf 命令未找到，请先安装 magic-pdf")
            return False


def convert_pdf(
    input_pdf: Path,
    output_dir: Path,
    output_filename: str,
    enable_images: bool,
    engine: str,
    timeout: int,
    model_source: str,
    proxy: str | None,
) -> tuple[bool, str, str]:
    """调用 MinerU 进行 PDF 转换。

    Args:
        input_pdf: 输入 PDF 文件路径
        output_dir: 输出目录
        output_filename: 输出文件名
        enable_images: 是否输出图片
        engine: 转换引擎
        timeout: 超时时间（秒）
        model_source: 模型源
        proxy: 代理地址

    Returns:
        (is_success, error_msg, hint_msg)
    """
    temp_output_dir = output_dir / f".ptm_temp_{int(time.time())}"
    temp_output_dir.mkdir(parents=True, exist_ok=True)

    cmd = ["magic-pdf", "-p", str(input_pdf), "-o", str(temp_output_dir), "-m", "auto"]

    logger.info(f"开始转换 PDF: {input_pdf}")
    logger.info(f"命令: {' '.join(cmd)}")

    process = None
    try:
        with console.status("[bold green]正在转换 PDF...", spinner="dots"):
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.warning(f"转换超时（{timeout}秒），正在终止进程...")
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("进程未响应 SIGTERM，发送 SIGKILL")
                    process.kill()
                    process.wait()

                _cleanup_temp_dir(temp_output_dir)
                return (
                    False,
                    f"ERROR: 转换超时（{timeout}秒）",
                    "HINT: 尝试增加 --timeout 参数或检查 PDF 文件大小",
                )

            if stderr:
                print(stderr, file=sys.stderr, end="")

            if process.returncode != 0:
                logger.error(f"MinerU 转换失败，退出码: {process.returncode}")
                _cleanup_temp_dir(temp_output_dir)
                return False, "ERROR: MinerU 转换失败", "HINT: 请查看上方日志了解详细错误信息"

    except FileNotFoundError:
        _cleanup_temp_dir(temp_output_dir)
        return (
            False,
            "ERROR: magic-pdf 命令未找到",
            "HINT: 请先安装 magic-pdf: pip install magic-pdf[full]",
        )
    except Exception as e:
        logger.exception(f"转换过程中发生异常: {e}")
        if process and process.poll() is None:
            process.kill()
        _cleanup_temp_dir(temp_output_dir)
        return False, f"ERROR: 转换失败: {e}", "HINT: 请查看上方日志了解详细错误信息"

    success = _process_output(temp_output_dir, output_dir, output_filename, enable_images)
    _cleanup_temp_dir(temp_output_dir)

    if success:
        logger.info(f"转换完成: {output_dir / output_filename}")
        return True, "", ""
    else:
        return False, "ERROR: 处理输出文件失败", "HINT: 请检查 MinerU 输出格式"


def _process_output(
    temp_dir: Path, output_dir: Path, output_filename: str, enable_images: bool
) -> bool:
    """处理 MinerU 输出文件。

    Args:
        temp_dir: 临时输出目录
        output_dir: 最终输出目录
        output_filename: 输出文件名
        enable_images: 是否保留图片

    Returns:
        是否成功
    """
    md_files = list(temp_dir.rglob("*.md"))
    if not md_files:
        logger.error(f"未找到 markdown 文件: {temp_dir}")
        return False

    source_md = md_files[0]
    target_md = output_dir / output_filename

    if enable_images:
        source_imgs_dir = source_md.parent / "images"
        if source_imgs_dir.exists():
            target_imgs_dir = output_dir / "imgs"
            shutil.copytree(source_imgs_dir, target_imgs_dir)
            logger.info(f"图片已复制到: {target_imgs_dir}")

            content = source_md.read_text(encoding="utf-8")
            content = content.replace("](images/", "](./imgs/")
            target_md.write_text(content, encoding="utf-8")
        else:
            shutil.copy2(source_md, target_md)
            logger.warning("未找到图片目录")
    else:
        content = source_md.read_text(encoding="utf-8")
        content = re.sub(r"!\[.*?\]\(.*?\)", "", content)
        target_md.write_text(content, encoding="utf-8")
        logger.info("已移除图片引用")

    return True


def _cleanup_temp_dir(temp_dir: Path) -> None:
    """清理临时目录。"""
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
            logger.debug(f"已清理临时目录: {temp_dir}")
        except Exception as e:
            logger.warning(f"清理临时目录失败: {e}")
