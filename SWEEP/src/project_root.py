"""定位 checkout 中的 SWEEP 数据目录。

PyBits 全局命令可以从任意当前目录运行。因此 SWEEP 会查找 editable install
来源，确保仍能定位源码 checkout 中的 `SWEEP/setting.yaml` 和 `SWEEP/_cache/`。
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
from pathlib import Path
from urllib.parse import unquote, urlparse


def find_sweep_data_dir() -> Path:
    """
    从 editable install 或源码树返回 SWEEP 数据目录。

    Returns:
        包含 `setting.yaml` 的 SWEEP 数据目录。
    """
    install_origin = _find_install_origin()
    if install_origin is not None:
        candidate = install_origin / "SWEEP"
        if (candidate / "setting.yaml").is_file():
            return candidate.resolve()

    return Path(__file__).resolve().parents[1]


def _find_install_origin() -> Path | None:
    """读取已安装 `pybits` 包中的 PEP 610 direct-url 元数据。"""
    try:
        distribution = importlib_metadata.distribution("pybits")
    except importlib_metadata.PackageNotFoundError:
        return None

    direct_url_text = distribution.read_text("direct_url.json")
    if not direct_url_text:
        return None

    try:
        direct_url_data = json.loads(direct_url_text)
    except json.JSONDecodeError:
        return None

    url = direct_url_data.get("url")
    if not isinstance(url, str):
        return None

    parsed_url = urlparse(url)
    if parsed_url.scheme != "file":
        return None

    return Path(unquote(parsed_url.path)).expanduser().resolve()
