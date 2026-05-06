# 测试指南

> 本文件范围：Python 测试模式与策略（pytest 配置、核心模式、测试原则）。
> 不在本文件范围：CI 测试流水线、Hypothesis 属性测试、性能基准测试。

## pytest 配置

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.coverage.run]
branch = true
source = ["src"]
```

## 核心模式

### 基本断言

```python
def test_encode():
    result = encode("hello")
    assert isinstance(result, str)
    assert result == "aGVsbG8="
```

### 参数化测试

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "aGVsbG8="),
    ("", ""),
    ("世界", "5LiW55WM"),
])
def test_encode_cases(input, expected):
    assert encode(input) == expected
```

### Fixture

```python
@pytest.fixture
def sample_data():
    return {"name": "test", "value": 42}

def test_with_fixture(sample_data):
    assert sample_data["value"] == 42
```

### Mock

```python
def test_api_call(mocker):
    mocker.patch("mylib.api.fetch", return_value={"status": "ok"})
    result = process()
    assert result == "ok"
```

### 异常测试

```python
def test_invalid_input():
    with pytest.raises(ValueError, match="must be positive"):
        validate(-1)
```

## 测试原则

| 原则 | 含义 |
|---|---|
| 独立 | 测试间无共享状态，执行顺序无关 |
| 确定性 | 每次运行结果相同，不依赖时间/随机/网络 |
| 快速 | 单元测试 < 100ms，慢测试归入集成测试 |
| 聚焦 | 测试行为而非实现，一个测试验证一个行为 |

## 覆盖率基础

- `pytest --cov=my_library`：运行并统计覆盖率。
- `--cov-branch`：启用分支覆盖（比行覆盖更严格）。
- `--cov-fail-under=80`：覆盖率低于阈值时失败。
- 覆盖率是信号不是目标——100% 覆盖不等于无 bug。
