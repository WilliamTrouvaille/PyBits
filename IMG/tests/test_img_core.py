"""IMG 核心逻辑的轻量回归测试。"""

from __future__ import annotations

import base64
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from IMG.src.config import load_provider_config, mask_token, normalize_base_url  # noqa: E402
from IMG.src.models import GeneratedImage, IMGError  # noqa: E402
from IMG.src.output import (  # noqa: E402
    build_output_paths,
    write_base64_images,
    write_generated_images,
)
from IMG.src.workflow import build_generate_plan, print_dry_run  # noqa: E402


@contextlib.contextmanager
def chdir(path: Path):
    """临时切换当前工作目录。"""

    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def write_env(root: Path, content: str) -> None:
    """写入测试用 IMG/.env。"""

    env_dir = root / "IMG"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / ".env").write_text(content.strip() + "\n", encoding="utf-8")


def args(**overrides: object) -> SimpleNamespace:
    """构造 generate 命令测试参数。"""

    defaults: dict[str, object] = {
        "prompt": "test prompt",
        "prompt_file": None,
        "out": "out.png",
        "provider": None,
        "model": None,
        "size": "auto",
        "quality": "medium",
        "output_format": "png",
        "n": 1,
        "force": False,
        "dry_run": True,
        "request_timeout": 120.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class IMGCoreTests(unittest.TestCase):
    def test_default_provider_uses_env_default(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_env(
                root,
                """
                IMG_PROVIDER_NAMES=main,backup
                IMG_DEFAULT_PROVIDER=backup
                IMG_MAIN_BASE_URL=https://main.example/v1
                IMG_MAIN_API_KEY=main-key
                IMG_MAIN_MODEL=gpt-image-2
                IMG_BACKUP_BASE_URL=https://backup.example/v1
                IMG_BACKUP_API_KEY=backup-key
                IMG_BACKUP_MODEL=gpt-image-2
                """,
            )
            with chdir(root):
                provider = load_provider_config()

        self.assertEqual(provider.name, "backup")
        self.assertEqual(provider.base_url, "https://backup.example/v1")

    def test_base_url_without_v1_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_env(
                root,
                """
                IMG_PROVIDER_NAMES=main
                IMG_MAIN_BASE_URL=https://main.example
                IMG_MAIN_API_KEY=main-key
                IMG_MAIN_MODEL=gpt-image-2
                """,
            )
            with chdir(root):
                provider = load_provider_config()

        self.assertEqual(provider.base_url, "https://main.example/v1")

    def test_normalize_base_url_variants(self) -> None:
        self.assertEqual(normalize_base_url("https://api.example"), "https://api.example/v1")
        self.assertEqual(normalize_base_url("https://api.example/"), "https://api.example/v1")
        self.assertEqual(normalize_base_url("https://api.example/v1"), "https://api.example/v1")
        self.assertEqual(
            normalize_base_url("https://api.example/openai"),
            "https://api.example/openai/v1",
        )
        self.assertEqual(normalize_base_url("api.example"), "https://api.example/v1")

    def test_provider_argument_overrides_default(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_env(
                root,
                """
                IMG_PROVIDER_NAMES=main,backup
                IMG_DEFAULT_PROVIDER=main
                IMG_MAIN_BASE_URL=https://main.example/v1
                IMG_MAIN_API_KEY=main-key
                IMG_MAIN_MODEL=gpt-image-2
                IMG_BACKUP_BASE_URL=https://backup.example/v1
                IMG_BACKUP_API_KEY=backup-key
                IMG_BACKUP_MODEL=gpt-image-2
                """,
            )
            with chdir(root):
                provider = load_provider_config("backup")

        self.assertEqual(provider.name, "backup")

    def test_missing_selected_provider_field_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_env(
                root,
                """
                IMG_PROVIDER_NAMES=main
                IMG_MAIN_BASE_URL=https://main.example/v1
                IMG_MAIN_API_KEY=main-key
                """,
            )
            with chdir(root), self.assertRaises(IMGError):
                load_provider_config()

    def test_mask_token(self) -> None:
        self.assertEqual(mask_token("1234567890"), "1234...7890")
        self.assertEqual(mask_token("short"), "*****")

    def test_build_generate_plan_uses_cli_model_override(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_env(
                root,
                """
                IMG_PROVIDER_NAMES=main
                IMG_MAIN_BASE_URL=https://main.example/v1
                IMG_MAIN_API_KEY=main-key
                IMG_MAIN_MODEL=gpt-image-2
                """,
            )
            with chdir(root):
                plan = build_generate_plan(args(model="custom-image-model"))

        self.assertEqual(plan.payload["model"], "custom-image-model")
        self.assertEqual(plan.payload["prompt"], "test prompt")
        self.assertEqual(plan.output_paths, [Path("out.png")])

    def test_dry_run_output_omits_base_url_and_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_env(
                root,
                """
                IMG_PROVIDER_NAMES=main
                IMG_MAIN_BASE_URL=https://main.example
                IMG_MAIN_API_KEY=main-secret-key
                IMG_MAIN_MODEL=gpt-image-2
                """,
            )
            with chdir(root):
                plan = build_generate_plan(args())

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            print_dry_run(plan)

        output = buffer.getvalue()
        self.assertNotIn("main.example", output)
        self.assertNotIn("main-secret-key", output)
        self.assertIn('"provider": "main"', output)

    def test_output_paths_for_multiple_images(self) -> None:
        paths = build_output_paths("result.png", "png", 3)
        self.assertEqual(paths, [Path("result-1.png"), Path("result-2.png"), Path("result-3.png")])

    def test_existing_output_without_force_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "exists.png"
            target.write_bytes(b"old")
            encoded = base64.b64encode(b"new").decode("ascii")
            with self.assertRaises(IMGError):
                write_base64_images([encoded], [target], force=False)

    def test_write_base64_images(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "image.png"
            encoded = base64.b64encode(b"image-bytes").decode("ascii")
            written = write_base64_images([encoded], [target], force=False)

            self.assertEqual(written, [target])
            self.assertEqual(target.read_bytes(), b"image-bytes")

    def test_write_url_image(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "image.png"
            response = Mock()
            response.status_code = 200
            response.iter_content.return_value = [b"image-", b"bytes"]

            with patch("IMG.src.output.requests.get", return_value=response) as get:
                written = write_generated_images(
                    [GeneratedImage(source="url", value="https://image.example/signed")],
                    [target],
                    force=False,
                    download_timeout=10.0,
                )

            get.assert_called_once()
            response.close.assert_called_once()
            self.assertEqual(written, [target])
            self.assertEqual(target.read_bytes(), b"image-bytes")


if __name__ == "__main__":
    unittest.main()
