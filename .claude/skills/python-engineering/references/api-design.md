# API 设计

> 本文件范围：Python 库 API 设计原则（渐进披露、命名、错误处理、反模式）。
> 不在本文件范围：API 版本迁移策略、Builder/Factory 等高级模式、Web API 设计。

## 渐进披露模式

API 按三层深度组织，让简单的事简单，复杂的事可能：

1. **简单函数**：`from mylib import encode, decode`——开箱即用，零配置。
2. **可配置类**：`encoder = Encoder(precision=15, cache=True)`——需要调参时升级到类。
3. **底层访问**：`from mylib.internals import BitEncoder`——高级场景显式导入，不污染顶层命名空间。

## 命名约定

| 用途 | 模式 | 示例 |
|---|---|---|
| 动作 | 动词 | `encode()`, `decode()`, `validate()` |
| 获取 | `get_*` | `get_config()`, `get_default()` |
| 布尔判断 | `is_*` / `has_*` / `can_*` | `is_valid()`, `has_permission()` |
| 转换 | `to_*` / `from_*` | `to_dict()`, `from_config()` |

## 错误处理

自定义异常基类 + `hint` 关键字参数，提供可操作建议：

```python
class MyLibraryError(Exception):
    def __init__(self, message: str, *, hint: str = ""):
        super().__init__(message)
        self.hint = hint
        # hint 不加入异常消息，供日志/UI 单独读取

raise ValidationError(
    "Latitude must be in [-90, 90]",
    hint="Did you swap latitude and longitude?"
)
```

## 废弃模式

```python
import warnings

def old_function():
    warnings.warn(
        "old_function is deprecated, use new_function instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return new_function()
```

## 反模式

### 布尔陷阱

位置布尔参数无法从调用处推断意图：

```python
# Bad
process(data, True, False)

# Good
process(data, validate=True, cache=False)
```

### 可变默认参数

默认可变对象在调用间共享状态：

```python
# Bad
def process(items=[]):

# Good
def process(items=None):
    if items is None:
        items = []
```
