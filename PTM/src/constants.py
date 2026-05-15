"""Constants for PTM."""

from __future__ import annotations

API_BASE_URL = "https://mineru.net"
BATCH_UPLOAD_ENDPOINT = "/api/v4/file-urls/batch"
BATCH_RESULT_ENDPOINT_TEMPLATE = "/api/v4/extract-results/batch/{batch_id}"

REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_POLL_INTERVAL_SECONDS = 3
DEFAULT_MODEL_VERSION = "vlm"
DEFAULT_LANGUAGE = "ch"

MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024
MAX_FILE_SIZE_MB = 200
MAX_PAGE_COUNT = 600
MAX_UNZIPPED_SIZE_BYTES = 1024 * 1024 * 1024

DOTENV_TOKEN_NAME = "MINERU_API_TOKEN"

SUCCESS_STATES = {"done"}
FAILED_STATES = {"failed"}
PENDING_STATES = {"waiting-file", "pending", "running", "converting"}
