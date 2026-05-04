"""敏感信息处理"""

from __future__ import annotations

from typing import Any

from .constants import SECRET_KEY_HINTS


def is_sensitive_key(key: str) -> bool:
    """
    判断键名是否为敏感信息（密钥、令牌等）

    Args:
        key: 键名

    Returns:
        如果键名包含敏感关键词则返回 True
    """
    lowered = key.lower()
    return any(hint in lowered for hint in SECRET_KEY_HINTS)


def redact(obj: Any, parent_key: str = "") -> Any:
    """
    递归脱敏对象中的敏感信息

    将包含敏感关键词的键对应的值替换为 "<redacted>"，
    同时截断过长的字符串（超过 300 字符）

    Args:
        obj: 待脱敏的对象（dict、list 或其他类型）
        parent_key: 父级键名，用于判断嵌套结构中的敏感字段

    Returns:
        脱敏后的对象
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            key = str(k)
            if is_sensitive_key(key):
                # 敏感键直接替换为 <redacted>
                out[key] = "<redacted>"
            else:
                # 递归处理值
                out[key] = redact(v, key)
        return out

    if isinstance(obj, list):
        # 递归处理列表元素
        return [redact(v, parent_key) for v in obj]

    if isinstance(obj, str):
        # 如果父键是敏感键，则脱敏
        if is_sensitive_key(parent_key):
            return "<redacted>"
        # 截断过长的字符串
        if len(obj) > 300:
            return obj[:200] + "...<truncated>"
        return obj

    return obj


def parse_header_names_from_string(value: str) -> list[str]:
    """
    从字符串中解析 HTTP header 名称

    解析 "Key: Value" 格式的 header 字符串，提取所有键名

    Args:
        value: 包含 header 的字符串

    Returns:
        去重并排序后的 header 名称列表
    """
    names: list[str] = []
    for line in value.splitlines():
        if ":" in line:
            name = line.split(":", 1)[0].strip()
            if name:
                names.append(name)
    return sorted(set(names))


def collect_header_sources(obj: Any, prefix: str = "") -> list[dict[str, Any]]:
    """
    递归收集配置对象中的 HTTP header 源

    遍历配置对象，找到所有包含 "headers" 关键词的字段，
    并记录其路径、类型和键名（值已脱敏）

    Args:
        obj: 配置对象（dict、list 或其他类型）
        prefix: 当前路径前缀，用于记录字段位置

    Returns:
        header 源信息列表，每个元素包含 path、kind、keys、values_redacted 字段
    """
    found: list[dict[str, Any]] = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            path = f"{prefix}.{key}" if prefix else key
            lowered = key.lower()

            # 检查键名是否包含 "headers"
            if "headers" in lowered:
                if isinstance(v, dict):
                    # header 是字典类型
                    found.append(
                        {
                            "path": path,
                            "kind": "map",
                            "keys": sorted(str(x) for x in v.keys()),
                            "values_redacted": True,
                        }
                    )
                elif isinstance(v, str):
                    # header 是字符串类型
                    found.append(
                        {
                            "path": path,
                            "kind": "string",
                            "keys": parse_header_names_from_string(v),
                            "values_redacted": True,
                        }
                    )
                else:
                    # 其他类型
                    found.append(
                        {
                            "path": path,
                            "kind": type(v).__name__,
                            "keys": [],
                            "values_redacted": True,
                        }
                    )

            # 递归处理嵌套结构
            found.extend(collect_header_sources(v, path))

    elif isinstance(obj, list):
        # 递归处理列表元素
        for idx, v in enumerate(obj):
            found.extend(collect_header_sources(v, f"{prefix}[{idx}]"))

    return found
