"""MinerU API 客户端。"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .constants import (
    API_BASE_URL,
    BATCH_RESULT_ENDPOINT_TEMPLATE,
    BATCH_UPLOAD_ENDPOINT,
    FAILED_STATES,
    PENDING_STATES,
    REQUEST_TIMEOUT_SECONDS,
    SUCCESS_STATES,
)
from .models import PTMError


class MinerUAPIClient:
    """
    封装 MinerU 精准解析 API 的任务创建、上传和轮询流程。
    """

    def __init__(self, token: str, proxy: str | None = None) -> None:
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.proxies = {"http": proxy, "https": proxy} if proxy else None

    def create_batch_task(
        self,
        pdf_path: Path,
        *,
        model_version: str,
        lang: str,
        is_ocr: bool,
        enable_table: bool,
        enable_formula: bool,
        page_ranges: str | None,
    ) -> tuple[str, str]:
        """
        创建 MinerU 批量任务并返回任务 ID 与签名上传 URL。

        Args:
            pdf_path: 待上传 PDF 路径。
            model_version: MinerU 模型版本。
            lang: 语言代码。
            is_ocr: 是否启用 OCR。
            enable_table: 是否启用表格识别。
            enable_formula: 是否启用公式识别。
            page_ranges: 可选页码范围。

        Returns:
            `(batch_id, signed_upload_url)` 元组。

        Raises:
            PTMError: API 响应缺少任务信息或上传 URL。
        """

        file_payload: dict[str, Any] = {
            "name": pdf_path.name,
            "is_ocr": is_ocr,
        }
        if page_ranges:
            file_payload["page_ranges"] = page_ranges

        payload = {
            "files": [file_payload],
            "model_version": model_version,
            "language": lang,
            "enable_table": enable_table,
            "enable_formula": enable_formula,
        }

        logger.info("创建 MinerU 批量解析任务")
        data = self._request_json(
            "POST",
            f"{API_BASE_URL}{BATCH_UPLOAD_ENDPOINT}",
            json=payload,
        )

        task_data = data.get("data")
        if not isinstance(task_data, dict):
            raise PTMError(
                "API 响应缺少任务数据",
                "稍后重试，或检查 MinerU API 状态。",
            )

        batch_id = str(task_data.get("batch_id") or "")
        file_urls = task_data.get("file_urls")
        if not batch_id or not isinstance(file_urls, list) or not file_urls:
            raise PTMError(
                "API 响应缺少上传 URL",
                "稍后重试，或检查 MinerU API 状态。",
            )

        signed_upload_url = str(file_urls[0])
        logger.info(f"任务已创建: batch_id={batch_id}")
        return batch_id, signed_upload_url

    def upload_file(self, signed_url: str, pdf_path: Path) -> None:
        """
        将本地 PDF 上传到 MinerU 返回的签名 URL。

        Args:
            signed_url: MinerU 返回的签名上传 URL。
            pdf_path: 本地 PDF 路径。

        Raises:
            PTMError: 文件读取、网络请求或上传状态码失败。
        """

        logger.info(f"上传 PDF: {pdf_path.name}")
        try:
            with pdf_path.open("rb") as file:
                response = requests.put(
                    signed_url,
                    data=file,
                    proxies=self.proxies,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
        except requests.RequestException as exc:
            raise PTMError(
                f"上传失败: {_safe_request_error(exc)}",
                "检查网络连接后重试。",
            ) from exc
        except OSError as exc:
            raise PTMError(
                f"无法读取待上传文件: {pdf_path}",
                f"检查文件权限后重试。细节: {exc}",
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise PTMError(
                f"上传失败: HTTP {response.status_code}",
                "检查网络连接后重试。",
            )
        logger.info("PDF 上传完成")

    def poll_result(
        self,
        batch_id: str,
        *,
        timeout: int,
        poll_interval: int,
    ) -> str:
        """
        轮询 MinerU 批量任务，直到返回结果 zip URL。

        Args:
            batch_id: MinerU 批量任务 ID。
            timeout: 最大等待时间，单位秒。
            poll_interval: 轮询间隔，单位秒。

        Returns:
            MinerU 结果 zip URL。

        Raises:
            PTMError: 参数无效、任务失败、超时或结果 URL 缺失。
        """

        if timeout <= 0:
            raise PTMError("--timeout 必须大于 0", "使用正整数作为 --timeout。")
        if poll_interval <= 0:
            raise PTMError(
                "--poll-interval 必须大于 0",
                "使用正整数作为 --poll-interval。",
            )

        deadline = time.monotonic() + timeout
        last_state = ""
        console = Console(stderr=True)

        logger.info("等待 MinerU 解析结果")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
            disable=not sys.stderr.isatty(),
        ) as progress:
            task_id = progress.add_task("等待解析结果", total=None)

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PTMError(
                        f"等待 MinerU 结果超时: {timeout} 秒",
                        "尝试增大 --timeout，或检查 PDF 复杂度。",
                    )

                result = self._get_batch_result(batch_id)
                state = str(result.get("state") or "pending")

                if state != last_state:
                    logger.info(f"任务状态: {state}")
                    last_state = state
                progress.update(task_id, description=f"任务状态: {state}")

                if state in SUCCESS_STATES:
                    zip_url = str(result.get("full_zip_url") or "")
                    if not zip_url:
                        raise PTMError(
                            "API 已处理完成，但缺少结果 zip URL",
                            "稍后重试，或联系 MinerU 支持。",
                        )
                    logger.info("MinerU 解析完成")
                    return zip_url

                if state in FAILED_STATES:
                    message = str(result.get("err_msg") or result.get("message") or "unknown error")
                    raise PTMError(
                        f"API 处理失败: {message}",
                        "检查 PDF 格式后重试。",
                    )

                if state not in PENDING_STATES:
                    logger.warning(f"未知任务状态，将继续轮询: {state}")

                time.sleep(min(poll_interval, max(deadline - time.monotonic(), 0.1)))

    def refresh_result_zip_url(self, batch_id: str) -> str:
        """
        为已创建的 MinerU 批量任务重新获取当前结果 zip URL。

        Args:
            batch_id: MinerU 批量任务 ID。

        Returns:
            当前可用的结果 zip URL。

        Raises:
            PTMError: 任务失败、未完成或响应缺少 URL。
        """

        logger.info(f"重新拉取 MinerU 结果 URL: batch_id={batch_id}")
        result = self._get_batch_result(batch_id)
        state = str(result.get("state") or "pending")

        if state in SUCCESS_STATES:
            zip_url = str(result.get("full_zip_url") or "")
            if not zip_url:
                raise PTMError(
                    "API 已处理完成，但缺少结果 zip URL",
                    "稍后重试，或联系 MinerU 支持。",
                )
            return zip_url

        if state in FAILED_STATES:
            message = str(result.get("err_msg") or result.get("message") or "unknown error")
            raise PTMError(
                f"API 处理失败: {message}",
                "检查 PDF 格式后重试。",
            )

        raise PTMError(
            f"API 处理结果尚未就绪: {state}",
            "等待后重试，或为这个 PDF 重新运行 PTM。",
        )

    def _get_batch_result(self, batch_id: str) -> dict[str, Any]:
        """
        获取并抽取指定批量任务的第一条结果。
        """

        url = f"{API_BASE_URL}{BATCH_RESULT_ENDPOINT_TEMPLATE.format(batch_id=batch_id)}"
        data = self._request_json("GET", url)
        return self._extract_first_result(data)

    def _request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """
        发送 MinerU API 请求并返回通过校验的 JSON 响应。
        """

        try:
            response = self.session.request(
                method,
                url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                proxies=self.proxies,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise PTMError(
                f"API 请求失败: {_safe_request_error(exc)}",
                "检查网络连接后重试。",
            ) from exc

        return self._check_response(response)

    def _check_response(self, response: requests.Response) -> dict[str, Any]:
        """
        校验 HTTP 状态码和 MinerU 业务状态码。
        """

        if response.status_code == 401:
            raise PTMError(
                "MinerU token 无效或已过期",
                "从 https://mineru.net 获取新 token，并更新 PTM/.env。",
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise PTMError(
                f"API 请求失败: HTTP {response.status_code}",
                "检查网络连接后重试。",
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise PTMError(
                "API 响应不是 JSON",
                "稍后重试，或检查 MinerU API 状态。",
            ) from exc

        code = data.get("code", 0)
        if str(code) in {"0", "200"}:
            return data

        message = str(data.get("msg") or data.get("message") or f"code {code}")
        code_text = str(code)
        if code_text in {"A0202", "A0211"}:
            raise PTMError(
                "MinerU token 无效或已过期",
                "从 https://mineru.net 获取新 token，并更新 PTM/.env。",
            )
        if code_text == "-60005":
            raise PTMError(
                "文件过大，MinerU 已拒绝该 PDF",
                "拆分或压缩 PDF 后重试。",
            )
        if code_text == "-60006":
            raise PTMError(
                "页数过多，MinerU 已拒绝该 PDF",
                "拆分 PDF，或使用 --page-ranges。",
            )

        raise PTMError(
            f"API 处理失败: {message}",
            "检查 PDF 格式后重试。",
        )

    @staticmethod
    def _extract_first_result(data: dict[str, Any]) -> dict[str, Any]:
        """
        从 MinerU 批量响应中抽取第一份文件结果。
        """

        task_data = data.get("data")
        if not isinstance(task_data, dict):
            return {"state": "pending"}

        results = task_data.get("extract_result") or task_data.get("extract_results")
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict):
                return first

        state = task_data.get("state")
        if state:
            return {"state": state}
        return {"state": "pending"}


def _safe_request_error(exc: requests.RequestException) -> str:
    """
    生成不会泄露签名 URL 查询串的请求错误摘要。
    """

    text = str(exc)
    request = getattr(exc, "request", None)
    url = getattr(request, "url", None)
    if url:
        text = text.replace(str(url), _redact_url(str(url)))
    return text


def _redact_url(url: str) -> str:
    """
    将 URL 缩减到 scheme 和 host，移除路径与查询串。
    """

    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return "[redacted-url]"
    return f"{parts.scheme}://{parts.netloc}/[redacted]"
