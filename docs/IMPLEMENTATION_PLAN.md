# 实现计划

## 任务 ID

T002

## 目标

修复 CLI 和 GUI 多批次合并默认读取 Excel 第一个工作表的问题，明确读取"财付通交易汇总"。当输入文件缺少该工作表时，返回清晰错误。

## 理解分析

当前两个多批次合并入口均使用 `pd.read_excel(filepath)` 读取 Excel，默认只读取第一个工作表。当历史输出文件存在其他附加工作表（如"停车缴费""特殊交易"等）在"财付通交易汇总"之前时，会读错数据。

具体定位：

1. **`scripts/app_merge.py` 第 83 行**：`pd.read_excel(filepath, dtype=str)` — 默认读取第一个 sheet，缺少 `sheet_name` 参数。

2. **`scripts/webui/bridge.py` 第 292 行**（`start_merge_process` 内部 `_run`）：`pd.read_excel(f, dtype=str)` — 同样默认读取第一个 sheet。

3. **错误处理**：两处均没有针对"目标工作表不存在"的特殊处理。`pd.read_excel` 在 sheet 不存在时会抛 `ValueError`，当前被笼统的 `except Exception` 捕获，用户看到的提示不够精确。

依赖关系：T002 依赖 T005（测试基础设施已就绪），可以添加测试验证本修复。

### 关键设计问题

- `bridge.py` 第 305-323 行在读取既往文件地点映射时已经显式指定了 `sheet_name="停车缴费"`，说明代码中有显式读取指定 sheet 的先例。
- `get_file_info()`（bridge.py 第 368 行）仅用于显示文件摘要信息（行数/列数），不是合并逻辑的一部分，按验收标准约束不在此次修复范围内。

## 预计变更的文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `scripts/app_merge.py` | 修改 — 1 行 | `pd.read_excel` 增加 `sheet_name="财付通交易汇总"` + ValueError 处理 |
| `scripts/webui/bridge.py` | 修改 — 2 行 | 合并路径的 `pd.read_excel` 增加 `sheet_name` 参数 + 精确错误提示 |
| `tests/test_merge_reader.py` | 新增 | 测试主工作表不在第一个位置的读取行为 |
| `docs/03_TASKS.md` | 修改 | 状态更新 |

## 实现策略

### 策略一：显式 sheet_name + 精确错误（代码修改）

**`app_merge.py` 修改方案：**

```python
# 第 81-88 行，原代码：
try:
    df = pd.read_excel(filepath, dtype=str)
    dfs.append(df)
    logger.info(f"  → {len(df)} 行, {len(df.columns)} 列")
except Exception as e:
    logger.error(f"读取失败: {filepath} - {e}")
    sys.exit(1)

# 修改为：
try:
    df = pd.read_excel(filepath, sheet_name="财付通交易汇总", dtype=str)
    dfs.append(df)
    logger.info(f"  → {len(df)} 行, {len(df.columns)} 列")
except ValueError as e:
    if "not found" in str(e) or "not exist" in str(e):
        logger.error(f"「财付通交易汇总」工作表不存在: {filepath}")
        print(f"❌ 文件缺少必要工作表「财付通交易汇总」: {os.path.basename(filepath)}")
    else:
        logger.error(f"读取失败: {filepath} - {e}")
    sys.exit(1)
except Exception as e:
    logger.error(f"读取失败: {filepath} - {e}")
    sys.exit(1)
```

**`bridge.py` 修改方案：**

```python
# 第 292 行，原代码：
df = pd.read_excel(f, dtype=str)

# 修改为：
try:
    df = pd.read_excel(f, sheet_name="财付通交易汇总", dtype=str)
except ValueError as e:
    if "not found" in str(e):
        progress.add_log(f"❌ 文件缺少必要工作表「财付通交易汇总」: {fname}")
    else:
        progress.add_log(f"❌ 读取失败: {fname} — {e}")
    progress.fail += 1
    continue
```

注意检查 `continue` 之后的逻辑流是否安全（当前循环体内有 `progress.success += 1` 和后续操作，continue 将跳过这些）。

### 策略二：测试方案（test_merge_reader.py）

新增测试文件 `tests/test_merge_reader.py`，使用 `pd.ExcelWriter` + `openpyxl` 构造具有多工作表的临时 Excel 文件，其中"财付通交易汇总"不在第一个位置，验证：
- 读取时指定 sheet_name 能正确读取目标工作表数据
- 文件缺少该工作表时 `pd.read_excel` 抛 `ValueError`

测试用例如下：
- `test_read_target_sheet_not_first`：构造多 sheet Excel，"财付通交易汇总"在第二个位置，验证能正确读取
- `test_missing_target_sheet_raises`：构造不含目标 sheet 的 Excel，验证抛出 ValueError

## 架构影响

无。仅修改两处 `pd.read_excel` 调用参数，不改变模块职责、不改变数据处理逻辑。

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| `bridge.py` 合并循环内 `continue` 跳过 `progress.success += 1` 逻辑 | 低 | 中 | 检查并确保 `continue` 前 progress 状态正确 |
| 已有历史文件的"财付通交易汇总"工作表名称不一致 | 低 | 低 | 当前版本输出的文件名称一致，只影响超旧版本；不兼容时可回退 |

## 测试策略

- 新增 `tests/test_merge_reader.py`（集成测试，真正读写 Excel 文件）
- 使用 `tempfile.TemporaryDirectory` 自动清理
- 已存在的 35 个测试不变

## 考虑的替代方案

1. **从文件名推断 sheet 名称**：不可靠，放弃。
2. **遍历 sheet 列表找到匹配名称**：`pd.read_excel` 本身已支持 `sheet_name` 参数，无需手动遍历。
3. **保持读取第一个 sheet 但增加警告日志**：不符合验收标准"显式读取"要求。

## 决策一致性

- 符合 ADR-002（CLI 与 GUI 共享核心处理管道），两处修改行为一致。
- 符合 ADR-004（自适应列名），这里不改变列识别，只改变工作表选取。
- 符合约束"不改变输出工作表命名"。

## 预估范围

| 维度 | 预估 |
|------|------|
| 修改文件 | 2 个 |
| 新增文件 | 1 个（测试） |
| 变更代码行 | ~15 行 |
| 新增测试用例 | 2 个 |
