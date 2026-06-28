# 实现计划

## 任务 ID

T004

## 目标

降低外部模型名称或接口变化导致地点识别不可用的风险，并提升错误提示质量。具体为：

1. 模型名不再只能通过修改代码调整，通过 JSON 配置文件管理
2. 日志记录实际请求的模型名称
3. HTTP 401、402、429、5xx 等错误向用户输出可理解信息
4. API 调用失败不影响主清洗输出（该点已在 pipeline.py 和 bridge.py 中实现，本次确认不变）

## 理解分析

### 当前问题

**问题 1：模型名硬编码**

`scripts/core/location.py` 第 33 行：

```python
MODEL = "deepseek-v4-pro"       # 硬编码，不可更改
```

注释自称"不可更改"，但 DeepSeek 模型名会随版本迭代变化（如 deepseek-chat、deepseek-reasoner 等）。一旦模型名变化，用户必须修改代码才能恢复功能。其他业务模块（parking、special_filter、mahjong、processor）均已使用 JSON 配置文件管理参数，唯独 location 模块使用硬编码常量。

此外，`MAX_WORKERS`、`CHUNK_SIZE`、`REQUEST_TIMEOUT`、`API_URL` 四个参数也硬编码在模块顶部，没有配置入口。

**问题 2：API 调用未记录模型名**

`_call_deepseek()` 函数在发送请求时将 `MODEL` 置于 payload 中，但日志仅输出 `"调用 DeepSeek API (N 条)..."`，未记录实际请求的模型名。如果模型名取自配置，配置与 API 实际使用的模型不一致时无法追溯。

**问题 3：HTTP 错误信息对用户不友好**

当前 `_call_deepseek()` 的 HTTP 错误处理（第 151-153 行）：

```python
except urllib.error.HTTPError as e:
    error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
    raise ValueError(f"API 返回 HTTP {e.code}: {error_body[:500]}") from e
```

所有 HTTP 状态码统一抛出 `ValueError`，其中：
- 401 — 用户不知是 API Key 无效
- 402 — 用户不知是余额不足
- 429 — 用户不知是频率超限
- 5xx — 用户看到技术性错误码无指导

**问题 4：API 调用失败不影响主输出（✅ 已验证）**

`pipeline.py:post_merge_analysis()` 第 64-74 行已用 `try/except` 包裹 `extract_locations`，`bridge.py:re_extract_locations()` 第 583-592 行也以 `try/except` 包裹并返回 error JSON。此项验收标准已满足，本次不做改动。

### 修正方向

1. 新建 `scripts/config/location_config.json`，将模型名和运行参数纳入配置
2. 按现有模块惯例在 `location.py` 中添加 `load_location_config()` 函数
3. `_call_deepseek()` 调用时从配置读取模型名，并在日志中记录
4. 分类处理 HTTP 状态码，输出用户可理解的说明
5. 补充测试：配置加载降级、错误信息格式

## 预计变更的文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `scripts/config/location_config.json` | 新增 | 地点识别配置文件（模型名、并发参数等） |
| `scripts/core/location.py` | 修改 | 硬编码常量 → 配置加载 + 日志记录模型 + 友好错误提示 |
| `docs/02_DECISIONS.md` | 修改 | 新增 ADR-007 记录地点识别配置结构 |
| `tests/test_location_error.py` | 新增 | 测试：配置降级、错误信息格式 |
| `docs/IMPLEMENTATION_PLAN.md` | 修改 | 本计划 |
| `docs/03_TASKS.md` | 修改 | 状态更新 |
| `docs/CHANGE_REPORT.md` | 新增（实现完成后） | 变更报告 |

## 实现策略

### Step 1：新增 `scripts/config/location_config.json`

遵循其他业务模块的配置惯例：

```json
{
  "model": "deepseek-v4-pro",
  "max_workers": 8,
  "chunk_size": 100,
  "request_timeout": 60
}
```

`API_URL` 暂保留硬编码（URL 变更场景远少于模型名，且引入配置会增加安全面），按任务范围仅将模型名和运行参数纳入配置。

### Step 2：添加 `load_location_config()`

在 `scripts/core/location.py` 中添加，遵循 `load_parking_config` 模式：

```python
def load_location_config(config_path: str | None = None) -> dict:
    """
    加载地点识别配置文件。

    Args:
        config_path: 配置文件路径，默认 scripts/config/location_config.json

    Returns:
        配置字典，包含 model, max_workers, chunk_size, request_timeout
    """
    if config_path is not None:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    from utils.config_loader import load_json_config
    return load_json_config("location_config", {
        "model": "deepseek-v4-pro",
        "max_workers": 8,
        "chunk_size": 100,
        "request_timeout": 60,
    })
```

### Step 3：修改常量为配置驱动

将模块顶部的硬编码常量替换为从配置加载的值：

- 移除 `MODEL`、`MAX_WORKERS`、`CHUNK_SIZE`、`REQUEST_TIMEOUT` 四个模块级硬编码常量
- 改为 `_config` 模块级变量，通过 `load_location_config()` 惰性加载
- 提供配置访问函数或直接引用字典值

设计选择：保持与现有其他模块一致的惰性加载模式——不在模块导入时加载配置，而是在 `extract_locations` 入口处或首次需要时加载。这样可以：

- 允许测试时传入自定义 config_path
- 避免模块导入顺序依赖
- 与 parking、special_filter 等模块的行为一致

### Step 4：API 调用日志记录模型名

在 `_call_deepseek()` 中，发送请求前增加日志：

```python
logger.info(f"DeepSeek API 请求: model={_config['model']}, notes={len(notes)} 条")
```

### Step 5：分类处理 HTTP 错误

将 `_call_deepseek()` 中的 `except HTTPError` 改为分类处理：

```python
except urllib.error.HTTPError as e:
    error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
    code = e.code
    if code == 401:
        msg = "API Key 无效或已过期，请在设置中重新填入有效的 DeepSeek API Key"
    elif code == 402:
        msg = "DeepSeek 账户余额不足，请前往 https://platform.deepseek.com 充值后重试"
    elif code == 429:
        msg = "请求频率超限（429），请稍后重试"
    elif 500 <= code < 600:
        msg = f"DeepSeek 服务器暂时不可用（HTTP {code}），请稍后重试"
    else:
        msg = f"API 请求失败（HTTP {code}）"
    # 附加响应体详细（如果有）
    if error_body:
        msg += f" — {error_body[:200]}"
    raise ValueError(msg) from e
```

### Step 6：更新 ADR

在 `docs/02_DECISIONS.md` 新增 ADR-007 记录配置结构决策。

### Step 7：添加测试

新增 `tests/test_location_error.py`，测试：

1. **`test_config_file_fallback`**：配置文件缺失时使用默认值
2. **`test_custom_config_path`**：传入自定义 config_path 可覆盖默认值
3. **`test_http_401_error_message`**：模拟 401 返回友好提示
4. **`test_http_402_error_message`**：模拟 402 返回友好提示
5. **`test_http_429_error_message`**：模拟 429 返回友好提示
6. **`test_http_5xx_error_message`**：模拟 503 返回友好提示

测试方式：不调用真实 API，直接测试 `_call_deepseek()` 在 HTTPError 下的行为，或测试 `load_location_config()` 的加载逻辑。需要将 `_call_deepseek` 中的 HTTP 调用设计为可模拟（通过参数注入 urlopen 或依赖注入）。

### 变更影响范围

- 只修改 `location.py` 一个源文件
- 对外接口（`extract_locations()` 签名）不变
- pipeline.py、bridge.py 无需修改
- 最终用户可通过编辑 `scripts/config/location_config.json` 修改模型名而无需接触代码

## 架构影响

小。新增一个业务配置文件（与其他模块一致），新增 ADR-007。不改变服务边界或通信模式。

## 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| 配置文件缺失或解析失败 | 使用硬编码默认值，行为不变 | `load_json_config` 已提供默认值 fallback |
| 模型名配置错误（如拼写） | API 返回 404 或错误 | 错误按分类处理，输出 HTTP 状态码和响应体，用户可自行修正配置 |
| `_call_deepseek` 测试需要模拟 HTTP | 测试复杂度增加 | 将 `urlopen` 设计为参数可注入，测试传入 mock |
| 用户升级后旧版无 config 文件 | 静默使用默认值 | 默认值与当前硬编码值一致，行为完全不变 |

## 测试策略

- 配置测试：构造/删除配置文件，验证加载结果和降级行为
- 错误消息测试：mock urllib.request.urlopen，抛出指定 HTTPError，验证异常消息包含友好提示
- 运行 `pytest tests/ -v` 确保无回归

## 考虑的替代方案

1. **仅提取模型名为模块级常量（不做配置文件）**：仍可通过修改代码调整，不能算"明确配置入口"。否决。

2. **通过 GUI 设置页面配置模型名**：增加前端交互复杂度，违反 ADR-005（基础功能不依赖 GUI）。否决。

3. **改用环境变量配置**：不符合项目现有配置惯例（统一使用 JSON 文件）。否决。

4. **将 API_URL 也纳入配置**：满足"接口变化"的防御场景更完整，但超出任务明确范围（任务要求"外部模型名称或接口变化"，任务标题强调"配置"）。按任务边界执行。

## 决策一致性

- 符合 ADR-001（Python/pandas 核心引擎）：配置加载沿用现有 JSON 模式。
- 符合 ADR-005（AI 地点识别可选）：错误处理增强不影响可选性。
- 符合现有模块模式（parking、special_filter、mahjong 均有自己的 JSON 配置文件）。
- 配置结构变更 → 需要更新 `docs/02_DECISIONS.md`（见 ADR-007）。

## 预估范围

- 新增文件：2 个（config JSON + 测试文件）
- 修改文件：3 个（location.py + 02_DECISIONS.md + 03_TASKS.md）
- 新增代码：约 120 行
