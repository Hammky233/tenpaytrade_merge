# 变更报告 — T004

## 变更的文件

| 文件 | 变更类型 |
|------|----------|
| `scripts/config/location_config.json` | 新增 — 地点识别配置文件 |
| `scripts/core/location.py` | 修改 — 配置驱动 + 模型名日志 + HTTP 错误分类处理 |
| `docs/02_DECISIONS.md` | 修改 — 新增 ADR-007 |
| `tests/test_location_error.py` | 新增 — 14 个测试用例 |
| `docs/CHANGE_REPORT.md` | 修改 — 本报告 |

## 变更摘要

将 DeepSeek 地点识别的模型名和运行参数从硬编码常量改为 JSON 配置文件管理，并提升错误提示的可观测性和可理解性。

### 具体修改

**`scripts/config/location_config.json`（新增）：**

```json
{
  "model": "deepseek-v4-pro",
  "max_workers": 8,
  "chunk_size": 100,
  "request_timeout": 60
}
```

与 `parking_config.json`、`special_filter_config.json` 等模块一致的 JSON 配置格式。通过 `--collect-data` 可自然包含在 PyInstaller 打包产物中。

**`scripts/core/location.py`：**

1. **新增 `load_location_config()`** — 遵循 `load_parking_config` 模式，支持可选 `config_path` 参数；文件缺失时使用 `utils.config_loader.load_json_config` 的硬编码默认值降级。
2. **新增 `_get_config()`** — 惰性加载缓存，首次调用后全局复用。
3. **替换硬编码常量**：`MODEL`、`MAX_WORKERS`、`CHUNK_SIZE`、`REQUEST_TIMEOUT` 四个模块级常量移除，改为从 `_get_config()` 字典读取。
4. **`_call_deepseek()` 增加 `_urlopen` 注入参数** — 默认 `urllib.request.urlopen`，测试时可传入 mock 避免真实网络请求。
5. **增加模型名日志** — 每次 API 调用前记录 `model=deepseek-v4-pro, notes=N 条, timeout=60s`。
6. **HTTP 错误分类处理**：

   | 状态码 | 用户提示 |
   |--------|----------|
   | 401 | API Key 无效或已过期 |
   | 402 | 账户余额不足，提供充值链接 |
   | 429 | 请求频率超限 |
   | 5xx | 服务器暂时不可用 |
   | 其他 | 通用 HTTP 错误提示 |
   | 所有 | 附加响应体前 200 字符详情 |

**`docs/02_DECISIONS.md` — 新增 ADR-007：**

记录地点 AI 识别配置使用 JSON 文件管理的决策背景、选型理由和后果。

### 未变更的行为

- `extract_locations()` 函数签名与行为完全不变
- `pipeline.py`、`bridge.py` 无需修改
- API Key 仍仅内存存储，不持久化
- AI 地点识别仍为可选功能
- 配置文件缺失时行为与之前完全一致（默认值相同）

## 添加的测试

**`tests/test_location_error.py`** — 14 个用例：

| 分类 | 测试 | 场景 |
|------|------|------|
| 配置加载 | `test_config_file_fallback` | 真实文件可读，键值类型合法 |
| | `test_config_file_custom_path` | 自定义路径覆盖默认值 |
| | `test_config_file_partial_override` | 部分字段覆盖（仅 model） |
| | `test_real_config_file_exists_and_valid` | 生产配置文件存在且 JSON 合法 |
| HTTP 错误 | `test_http_401_error_message` | 401 → 含"API Key"提示 |
| | `test_http_402_error_message` | 402 → 含"余额不足"和充值链接 |
| | `test_http_429_error_message` | 429 → 含"频率超限" |
| | `test_http_503_error_message` | 503 → 含"服务器暂时不可用" |
| | `test_http_500_error_message` | 500 → 含"服务器暂时不可用" |
| | `test_http_unknown_error_message` | 403 → 含 HTTP 状态码 |
| | `test_error_body_appended` | 响应体详情附加到提示信息 |
| | `test_empty_notes_returns_early` | 空输入不发起网络请求 |
| 集成 | `test_get_config_returns_valid_values` | `_get_config()` 返回合法值 |
| | `test_extract_locations_no_api_key_returns_early` | 空 DataFrame 提前返回 |

## 已执行的测试

```powershell
cd /d C:\CCProject\tenpaytrade_merge
.\.venv\Scripts\python -m pytest tests/ -v
```

结果：**60 passed** in 1.38s（新增 14 个，原有 46 个无回归）。

## 已知风险

- 若用户手动编辑 `location_config.json` 填入错误的模型名，API 调用会失败，错误信息会指示 HTTP 状态码和建议措施
- `_get_config()` 使用模块级全局缓存，测试间可能相互影响（当前所有配置测试独立运行，无冲突）
- `API_URL` 仍为硬编码：若 DeepSeek 变更 API 端点，仍需发版修改代码。该场景远少于模型名变更，按任务边界未纳入配置

## 经验教训

1. **配置管理应统一模式**：本项目 5 个业务模块中 4 个使用 JSON 配置，唯有 location 模块使用硬编码。新模块应及时对齐既有模式。
2. **HTTP 错误应区分给出 actionable 提示**：将 401/402/429/5xx 混合的 "API error" 消息拆分为有针对性的提示，能显著降低用户排查成本。
3. **测试 HTTP 错误无需 mock 框架**：通过 `_urlopen` 默认参数注入，测试直接传入抛出 HTTPError 的 lambda，代码零外部依赖。
