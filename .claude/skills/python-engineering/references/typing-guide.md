# 类型指南

> 本文件范围：Python 类型标注迁移与修复工作流（修复优先级、类型选择、温和立场、常见模式）。
> 不在本文件范围：特定类型检查器的安装与配置、非 Python 类型系统。

## 修复优先级（6 层）

修复类型错误时，从第 1 层开始逐层推进，不在低层完成前跳到高层：

1. **快速修复**：未使用的 import、缺失的返回类型、泛型参数缺失（`list` → `list[str]`）。
2. **标注完整性**：参数类型、类属性、模块级变量的类型标注。
3. **类型安全**：`None`/`Optional` 处理（早返回/默认值/raise）、`isinstance` 收窄、`Union` 处理。
4. **结构模式**：`TYPE_CHECKING` 条件导入、`TypedDict`、`Protocol`、dataclass field 默认值。
5. **外部依赖**：安装 stub 包（`types-requests`）、内联 `.pyi` 文件。
6. **边缘情况**：`TypeVar` bound、协变/逆变泛型、`@overload`、元编程。

## 类型选择指导

- **`object` 优于 `Any`**：`Any` 关闭类型检查，`object` 表示"任意值"但要求收窄后使用。
- **`isinstance()` 收窄优于 `cast()`**：运行时验证 vs. 强制转换——前者安全，后者绕过检查。
- **`TypeGuard`**：当 `isinstance` 无法表达收窄逻辑时使用（如验证 dict 结构）。

## 温和立场

本 skill 采用温和类型审查模式，区别于严格禁止模式：

- **允许附理由的 `# type: ignore`**：仅在安装 stub 包不可行时使用，必须附注释说明原因。
  ```python
  from untyped_lib import something  # type: ignore[import-untyped] # 该库无 stub 包
  ```
- **允许附上下文的 `assert`**：需要说明成立条件。
  ```python
  assert result is not None, "post-validation: caller guarantees non-None"
  ```
- **鼓励修复优于抑制**：优先添加类型标注、安装 stub 包、使用 isinstance 收窄。抑制是最后手段。
- **标记 `Any` 用法**：审查中发现 `Any` 时，建议 `object` 或更具体的类型替代，但不强制。

## 常见模式

### TYPE_CHECKING 条件导入

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mylib.types import HeavyType
```

### TypedDict 替代原始 dict

```python
from typing import TypedDict

class UserInfo(TypedDict):
    name: str
    age: int
```

### Protocol 替代鸭子类型

```python
from typing import Protocol

class Closeable(Protocol):
    def close(self) -> None: ...
```

### dataclass 可变默认参数

```python
from dataclasses import dataclass, field

@dataclass
class Config:
    items: list[str] = field(default_factory=list)  # 不用 items: list[str] = []
```

## 第三方库处理

按优先级处理无类型的第三方库：

1. **Stub 包优先**：`pip install types-requests`（查找 `types-*` 或 `*_stubs`）。
2. **内联 `.pyi` 文件次之**：在项目内创建最小 stub。
3. **`# type: ignore[import-untyped]` 最后**：仅当上述方法不可行，且必须附理由注释。

## 进度跟踪

批量类型修复时简要记录：

- 起始错误数 vs 当前错误数。
- 发现的修复模式（哪些层最多）。
- 未解决问题及原因（如第三方库无 stub）。
- 每修约 50 个错误后做一次一致性检查。
