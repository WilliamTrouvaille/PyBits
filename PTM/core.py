"""核心转换逻辑：模型检查下载、MinerU进程管理、超时控制、临时文件清理。"""

import json
import os
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

MINERU_MODEL_REPO = "opendatalab/PDF-Extract-Kit-1.0"
LAYOUTREADER_MODEL_REPO = "ppaanngggg/layoutreader"
PTM_CONFIG_DIR = Path.home() / ".cache" / "ptm"
PTM_MINERU_CONFIG = PTM_CONFIG_DIR / "magic-pdf.json"
MINERU_MODELSCOPE_MODEL_DIR = (
    Path.home()
    / ".cache"
    / "modelscope"
    / "hub"
    / "models"
    / "OpenDataLab"
    / "PDF-Extract-Kit-1___0"
    / "models"
)
MINERU_MODELSCOPE_LAYOUTREADER_DIR = (
    Path.home() / ".cache" / "modelscope" / "hub" / "models" / "ppaanngggg" / "layoutreader"
)
MINERU_HF_MODEL_DIR = (
    Path.home() / ".cache" / "huggingface" / "hub" / "models--opendatalab--PDF-Extract-Kit-1.0"
)
MINERU_HF_LAYOUTREADER_DIR = (
    Path.home() / ".cache" / "huggingface" / "hub" / "models--ppaanngggg--layoutreader"
)
MINERU_ALLOW_PATTERNS = [
    "models/Layout/YOLO/*",
    "models/MFD/YOLO/*",
    "models/MFR/unimernet_hf_small_2503/*",
    "models/OCR/paddleocr_torch/*",
]
MINERU_REQUIRED_MODEL_FILES = [
    "Layout/YOLO/doclayout_yolo_docstructbench_imgsz1280_2501.pt",
    "MFD/YOLO/yolo_v8_ft.pt",
    "MFR/unimernet_hf_small_2503/config.json",
    "MFR/unimernet_hf_small_2503/model.safetensors",
    "OCR/paddleocr_torch/ch_PP-OCRv4_rec_infer.pth",
]
LAYOUTREADER_REQUIRED_MODEL_FILES = [
    "config.json",
    "configuration.json",
    "pytorch_model.bin",
]


def _magic_pdf_executable() -> str:
    """返回当前运行环境中可用的 magic-pdf 可执行文件路径。"""
    executable_name = "magic-pdf.exe" if sys.platform == "win32" else "magic-pdf"
    local_executable = Path(sys.executable).with_name(executable_name)
    if local_executable.exists():
        return str(local_executable)

    resolved_executable = shutil.which("magic-pdf")
    if resolved_executable:
        return resolved_executable

    return executable_name


def _with_proxy_env(proxy: str | None) -> dict[str, str]:
    """返回带代理配置的环境变量副本。"""
    env = os.environ.copy()
    if proxy:
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy
    return env


def _magic_pdf_env(config_path: Path) -> dict[str, str]:
    """返回 magic-pdf 子进程环境。"""
    env = os.environ.copy()
    env["MINERU_TOOLS_CONFIG_JSON"] = str(config_path)
    return env


def _is_complete_model_dir(model_dir: Path) -> bool:
    """检查 MinerU 1.3.12 需要的关键模型文件是否存在。"""
    return all(
        (model_dir / relative_path).exists() for relative_path in MINERU_REQUIRED_MODEL_FILES
    )


def _is_complete_layoutreader_dir(model_dir: Path) -> bool:
    """检查 layoutreader 模型关键文件是否存在。"""
    return all(
        (model_dir / relative_path).exists()
        for relative_path in LAYOUTREADER_REQUIRED_MODEL_FILES
    )


def _write_mineru_config(model_dir: Path, layoutreader_model_dir: Path) -> Path:
    """写入 PTM 专用 MinerU 配置文件。"""
    PTM_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = {
        "bucket_info": {"[default]": ["", "", ""]},
        "models-dir": str(model_dir),
        "layoutreader-model-dir": str(layoutreader_model_dir),
        "device-mode": "cpu",
        "layout-config": {"model": "doclayout_yolo"},
        "formula-config": {
            "mfd_model": "yolo_v8_mfd",
            "mfr_model": "unimernet_small",
            "enable": True,
        },
        "table-config": {
            "model": "rapid_table",
            "sub_model": "slanet_plus",
            "enable": True,
            "max_time": 400,
        },
        "latex-delimiter-config": {
            "display": {"left": "$$", "right": "$$"},
            "inline": {"left": "$", "right": "$"},
        },
        "llm-aided-config": {
            "formula_aided": {
                "api_key": "",
                "base_url": "",
                "model": "",
                "enable": False,
            },
            "text_aided": {
                "api_key": "",
                "base_url": "",
                "model": "",
                "enable": False,
            },
            "title_aided": {
                "api_key": "",
                "base_url": "",
                "model": "",
                "enable": False,
            },
        },
        "config_version": "1.2.1",
    }
    PTM_MINERU_CONFIG.write_text(
        json.dumps(config, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )
    return PTM_MINERU_CONFIG


def _download_models_from_modelscope(proxy: str | None) -> tuple[Path, Path]:
    """从 ModelScope 下载 MinerU 模型。"""
    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise RuntimeError("缺少 modelscope 依赖，无法从 ModelScope 下载模型") from exc

    env = _with_proxy_env(proxy)
    old_env = {
        key: os.environ.get(key)
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
    }
    try:
        os.environ.update({key: value for key, value in env.items() if key in old_env})
        model_repo_dir = Path(
            snapshot_download(MINERU_MODEL_REPO, allow_patterns=MINERU_ALLOW_PATTERNS)
        )
        layoutreader_model_dir = Path(snapshot_download(LAYOUTREADER_MODEL_REPO))
    finally:
        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

    return model_repo_dir / "models", layoutreader_model_dir


def _download_models_from_huggingface(proxy: str | None) -> tuple[Path, Path]:
    """从 Hugging Face 下载 MinerU 模型。"""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("缺少 huggingface-hub 依赖，无法从 Hugging Face 下载模型") from exc

    env = _with_proxy_env(proxy)
    old_env = {
        key: os.environ.get(key)
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
    }
    try:
        os.environ.update({key: value for key, value in env.items() if key in old_env})
        model_repo_dir = Path(
            snapshot_download(repo_id=MINERU_MODEL_REPO, allow_patterns=MINERU_ALLOW_PATTERNS)
        )
        layoutreader_model_dir = Path(snapshot_download(repo_id=LAYOUTREADER_MODEL_REPO))
    finally:
        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

    return model_repo_dir / "models", layoutreader_model_dir


def prepare_mineru_runtime(
    model_source: str, proxy: str | None
) -> tuple[bool, Path | None, str, str]:
    """检查模型是否存在，不存在则下载。

    Args:
        model_source: 模型源（modelscope/huggingface）
        proxy: 代理地址

    Returns:
        (是否成功, MinerU 配置文件路径, error_msg, hint_msg)
    """
    if model_source == "modelscope":
        model_dir = MINERU_MODELSCOPE_MODEL_DIR
        layoutreader_model_dir = MINERU_MODELSCOPE_LAYOUTREADER_DIR
        download_models = _download_models_from_modelscope
    elif model_source == "huggingface":
        model_dir = MINERU_HF_MODEL_DIR
        layoutreader_model_dir = MINERU_HF_LAYOUTREADER_DIR
        download_models = _download_models_from_huggingface
    else:
        return (
            False,
            None,
            f"ERROR: 不支持的模型源: {model_source}",
            "HINT: 请使用 modelscope 或 huggingface",
        )

    if _is_complete_model_dir(model_dir) and _is_complete_layoutreader_dir(
        layoutreader_model_dir
    ):
        logger.info(f"模型已存在: {model_dir}")
    else:
        logger.info(f"模型不完整，开始从 {model_source} 下载 MinerU 模型")
        with console.status("[bold green]正在下载模型...", spinner="dots"):
            try:
                model_dir, layoutreader_model_dir = download_models(proxy)
            except Exception as exc:
                logger.exception(f"模型下载失败: {exc}")
                return (
                    False,
                    None,
                    "ERROR: 模型检查或下载失败",
                    f"HINT: 请检查网络、代理或模型源。详细错误: {exc}",
                )

        if not _is_complete_model_dir(model_dir):
            missing = [
                relative_path
                for relative_path in MINERU_REQUIRED_MODEL_FILES
                if not (model_dir / relative_path).exists()
            ]
            return (
                False,
                None,
                "ERROR: MinerU 模型文件不完整",
                f"HINT: 缺失文件: {', '.join(missing)}",
            )
        if not _is_complete_layoutreader_dir(layoutreader_model_dir):
            missing = [
                relative_path
                for relative_path in LAYOUTREADER_REQUIRED_MODEL_FILES
                if not (layoutreader_model_dir / relative_path).exists()
            ]
            return (
                False,
                None,
                "ERROR: layoutreader 模型文件不完整",
                f"HINT: 缺失文件: {', '.join(missing)}",
            )

    config_path = _write_mineru_config(model_dir, layoutreader_model_dir)
    logger.info(f"MinerU 配置文件: {config_path}")
    return True, config_path, "", ""


def convert_pdf(
    input_pdf: Path,
    output_dir: Path,
    output_filename: str,
    enable_images: bool,
    engine: str,
    timeout: int,
    model_source: str,
    proxy: str | None,
    mineru_config: Path,
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
        mineru_config: MinerU 配置文件路径

    Returns:
        (is_success, error_msg, hint_msg)
    """
    temp_output_dir = output_dir / f".ptm_temp_{int(time.time())}"
    temp_output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [_magic_pdf_executable(), "-p", str(input_pdf), "-o", str(temp_output_dir), "-m", "auto"]

    logger.info(f"开始转换 PDF: {input_pdf}")
    logger.info(f"命令: {' '.join(cmd)}")

    process = None
    try:
        with console.status("[bold green]正在转换 PDF...", spinner="dots"):
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=_magic_pdf_env(mineru_config),
            )

            try:
                _stdout, stderr = process.communicate(timeout=timeout)
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
