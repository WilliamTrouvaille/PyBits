"""IMG 图片生成工作流。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from loguru import logger

from .api_client import ImageAPIClient
from .config import load_provider_config
from .constants import MAX_VARIANTS, MIN_VARIANTS
from .models import GeneratePlan, IMGError, ProviderConfig
from .output import (
    build_output_paths,
    ensure_outputs_available,
    normalize_output_format,
    write_generated_images,
)


def generate_image(args: argparse.Namespace) -> list[Path]:
    """
    执行一次图片生成流程。

    Args:
        args: argparse 解析出的命名空间。

    Returns:
        生成或 dry-run 规划出的输出路径。
    """

    plan = build_generate_plan(args)
    logger.info(f"使用 provider: name={plan.provider.name}, model={plan.payload['model']}")

    if args.dry_run:
        print_dry_run(plan)
        return plan.output_paths

    client = ImageAPIClient(plan.provider, timeout_seconds=args.request_timeout)
    images = client.generate(plan.payload)
    written = write_generated_images(
        images,
        plan.output_paths,
        force=args.force,
        download_timeout=args.request_timeout,
    )
    logger.info(f"图片已写入: {', '.join(str(path) for path in written)}")
    return written


def build_generate_plan(args: argparse.Namespace) -> GeneratePlan:
    """
    构建一次图片生成请求的最终执行计划。
    """

    validate_runtime_options(args)
    provider = load_provider_config(args.provider)
    prompt = read_prompt(args.prompt, args.prompt_file)
    output_format = normalize_output_format(args.output_format)
    output_paths = build_output_paths(args.out, output_format, args.n)
    ensure_outputs_available(output_paths, force=args.force)
    payload = build_generate_payload(
        prompt=prompt,
        provider=provider,
        model_override=args.model,
        size=args.size,
        quality=args.quality,
        output_format=output_format,
        n=args.n,
    )
    return GeneratePlan(provider=provider, payload=payload, output_paths=output_paths)


def build_generate_payload(
    *,
    prompt: str,
    provider: ProviderConfig,
    model_override: str | None,
    size: str,
    quality: str,
    output_format: str,
    n: int,
) -> dict[str, Any]:
    """
    构建 OpenAI Images API 兼容的 generation payload。
    """

    model = (model_override or provider.model).strip()
    if not model:
        raise IMGError("未提供模型名称", "在 `.env` 中配置 MODEL，或使用 --model 覆盖。")

    return {
        "model": model,
        "prompt": prompt,
        "n": n,
        "size": size,
        "quality": quality,
        "output_format": output_format,
    }


def validate_runtime_options(args: argparse.Namespace) -> None:
    """
    校验运行时选项，避免在发送请求后才发现本地参数错误。
    """

    if args.n < MIN_VARIANTS or args.n > MAX_VARIANTS:
        raise IMGError(
            "--n 必须在 1 到 10 之间",
            "使用 1 到 10 之间的整数。",
        )
    if args.request_timeout <= 0:
        raise IMGError(
            "--request-timeout 必须大于 0",
            "使用正数作为请求超时时间。",
        )


def read_prompt(prompt: str | None, prompt_file: str | None) -> str:
    """
    从参数或文本文件读取提示词。
    """

    if prompt and prompt_file:
        raise IMGError(
            "--prompt 和 --prompt-file 不能同时使用",
            "二者选择一个即可。",
        )
    if prompt_file:
        path = Path(prompt_file).expanduser()
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise IMGError(
                f"无法读取提示词文件: {path}",
                f"检查文件路径和权限后重试。细节: {exc}",
            ) from exc
        if not text:
            raise IMGError(
                f"提示词文件为空: {path}",
                "在文件中写入图片生成提示词。",
            )
        return text

    if prompt and prompt.strip():
        return prompt.strip()

    raise IMGError(
        "缺少图片生成提示词",
        "使用 --prompt 或 --prompt-file 提供提示词。",
    )


def print_dry_run(plan: GeneratePlan) -> None:
    """
    输出 dry-run 请求摘要。
    """

    preview = {
        "provider": plan.provider.name,
        "endpoint": "/images/generations",
        "outputs": [str(path) for path in plan.output_paths],
        "payload": redact_payload_for_preview(plan.payload),
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2, sort_keys=True))


def redact_payload_for_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """
    生成适合终端展示的 payload 摘要。
    """

    preview = dict(payload)
    prompt = str(preview.get("prompt", ""))
    if len(prompt) > 120:
        preview["prompt"] = f"{prompt[:117]}..."
    return preview
