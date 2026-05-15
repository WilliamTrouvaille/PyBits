"""MinerU API client."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

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
    """Client for the MinerU precise parsing API."""

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
        """Create a MinerU batch task and return its id and upload URL."""

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
                "Unexpected API response: missing task data",
                "Try again later or check MinerU API status.",
            )

        batch_id = str(task_data.get("batch_id") or "")
        file_urls = task_data.get("file_urls")
        if not batch_id or not isinstance(file_urls, list) or not file_urls:
            raise PTMError(
                "Unexpected API response: missing upload URL",
                "Try again later or check MinerU API status.",
            )

        signed_upload_url = str(file_urls[0])
        logger.info(f"任务已创建: batch_id={batch_id}")
        return batch_id, signed_upload_url

    def upload_file(self, signed_url: str, pdf_path: Path) -> None:
        """Upload a local PDF to the signed upload URL."""

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
                f"Upload failed: {exc}",
                "Check network connection and try again.",
            ) from exc
        except OSError as exc:
            raise PTMError(
                f"Cannot read file for upload: {pdf_path}",
                f"Check file permissions and try again. Details: {exc}",
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise PTMError(
                f"Upload failed: HTTP {response.status_code}",
                "Check network connection and try again.",
            )
        logger.info("PDF 上传完成")

    def poll_result(
        self,
        batch_id: str,
        *,
        timeout: int,
        poll_interval: int,
    ) -> str:
        """Poll MinerU until the batch task returns a zip URL."""

        if timeout <= 0:
            raise PTMError("Invalid timeout: must be > 0", "Use --timeout with a positive integer.")
        if poll_interval <= 0:
            raise PTMError(
                "Invalid poll interval: must be > 0",
                "Use --poll-interval with a positive integer.",
            )

        url = f"{API_BASE_URL}{BATCH_RESULT_ENDPOINT_TEMPLATE.format(batch_id=batch_id)}"
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
                        f"Timeout after {timeout} seconds",
                        "Try increasing --timeout or check PDF complexity.",
                    )

                data = self._request_json("GET", url)
                result = self._extract_first_result(data)
                state = str(result.get("state") or "pending")

                if state != last_state:
                    logger.info(f"任务状态: {state}")
                    last_state = state
                progress.update(task_id, description=f"任务状态: {state}")

                if state in SUCCESS_STATES:
                    zip_url = str(result.get("full_zip_url") or "")
                    if not zip_url:
                        raise PTMError(
                            "API processing finished but zip URL is missing",
                            "Try again later or contact MinerU support.",
                        )
                    logger.info("MinerU 解析完成")
                    return zip_url

                if state in FAILED_STATES:
                    message = str(result.get("err_msg") or result.get("message") or "unknown error")
                    raise PTMError(
                        f"API processing failed: {message}",
                        "Check PDF format and try again.",
                    )

                if state not in PENDING_STATES:
                    logger.warning(f"未知任务状态，将继续轮询: {state}")

                time.sleep(min(poll_interval, max(deadline - time.monotonic(), 0.1)))

    def _request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
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
                f"API request failed: {exc}",
                "Check network connection and try again.",
            ) from exc

        return self._check_response(response)

    def _check_response(self, response: requests.Response) -> dict[str, Any]:
        if response.status_code == 401:
            raise PTMError(
                "Invalid or expired token",
                "Get a new token from https://mineru.net and update PTM/.env.",
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise PTMError(
                f"API request failed: HTTP {response.status_code}",
                "Check network connection and try again.",
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise PTMError(
                "Unexpected API response: not JSON",
                "Try again later or check MinerU API status.",
            ) from exc

        code = data.get("code", 0)
        if str(code) in {"0", "200"}:
            return data

        message = str(data.get("msg") or data.get("message") or f"code {code}")
        code_text = str(code)
        if code_text in {"A0202", "A0211"}:
            raise PTMError(
                "Invalid or expired token",
                "Get a new token from https://mineru.net and update PTM/.env.",
            )
        if code_text == "-60005":
            raise PTMError(
                "File too large: MinerU rejected the PDF",
                "Split the PDF or compress it.",
            )
        if code_text == "-60006":
            raise PTMError(
                "Too many pages: MinerU rejected the PDF",
                "Split the PDF or use --page-ranges.",
            )

        raise PTMError(
            f"API processing failed: {message}",
            "Check PDF format and try again.",
        )

    @staticmethod
    def _extract_first_result(data: dict[str, Any]) -> dict[str, Any]:
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
