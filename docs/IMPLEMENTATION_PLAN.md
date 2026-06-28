# 实现计划

## 任务 ID

T003

## 目标

修复 GUI「重新提取地点」功能在写回 Excel 时破坏所有工作表格式的问题。重新提取地点后，其他工作表的隐藏列、冻结窗格、列宽应原样保留；「停车缴费」工作表中非「地点」列的数据和单元格样式也应保持不变。

## 理解分析

### 问题根因

`scripts/webui/bridge.py: re_extract_locations()` 第 529–541 行的写回逻辑：

```python
with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
    for sheet_name, sheet_df in all_sheets.items():
        sheet_df.to_excel(writer, index=False, sheet_name=sheet_name)
```

`pd.ExcelWriter` 内部调用 `openpyxl.Workbook()` 创建**全新文件**，逐 sheet 写入只写数据，不携带任何格式。后续仅对「停车缴费」调用 `_format_worksheet` 恢复格式，其他 sheet 全部丢失格式化状态。

### 修正方向

不应删除并重写「停车缴费」整表数据行。改为按列原地更新——只操作「地点」列单元格，其他单元格完全不动。

具体操作：
1. `openpyxl.load_workbook(excel_path)` 完整加载工作簿（所有格式保留）
2. 定位 `wb["停车缴费"]` sheet
3. 按表头查找「地点」列索引；若不存在则新建列
4. 对第 2 行起每行，**仅**更新「地点」单元格的值
5. `extract_locations` 自身已保证已有非「无」值不被覆盖，原地写入不做额外覆盖
6. 若新增「地点」列，将原黄色标记区域扩展到新列单元格
7. 仅 `wb.save()`，其他 sheet 和单元格不受任何影响

## 预计变更的文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `scripts/webui/bridge.py` | 修改 | `re_extract_locations` 方法第 526-541 行改写为 openpyxl 按列原地更新 |
| `tests/test_excel_format_preserve.py` | 新增 | 测试原地更新后格式保留、非地点列未被修改 |
| `docs/IMPLEMENTATION_PLAN.md` | 修改 | 本计划 |
| `docs/03_TASKS.md` | 修改 | 状态更新 |
| `docs/CHANGE_REPORT.md` | 新增（实现完成后） | 变更报告 |

## 实现策略

### Step 1：改写 `bridge.py:re_extract_locations()` 写回逻辑

将第 526-541 行的 pd.ExcelWriter 全重写替换为 openpyxl 按列原地更新：

```python
# ── 5. 写回 Excel（原地更新，仅操作「停车缴费」sheet 的「地点」列）──
import openpyxl
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter, column_index_from_string
from core.writer import YELLOW_FILL

_sanitize_for_excel(parking_df)
wb = openpyxl.load_workbook(excel_path)
ws = wb["停车缴费"]

# 5a. 定位「地点」列索引 — 按表头名称查找
LOCATION_COL_NAME = "地点"
location_col_idx = None
for cell in ws[1]:
    if cell.value == LOCATION_COL_NAME:
        location_col_idx = cell.column
        break

# 5b. 若「地点」列不存在，在停车缴费表最右侧新建
if location_col_idx is None:
    location_col_idx = (ws.max_column or 0) + 1
    ws.cell(row=1, column=location_col_idx).value = LOCATION_COL_NAME

# 5c. 逐行只更新「地点」单元格
# parking_df 与 ws 的行对应关系：ws row=idx+2 ↔ parking_df index idx
for df_idx in range(len(parking_df)):
    excel_row = df_idx + 2  # 第1行是表头
    loc_value = parking_df.iloc[df_idx][LOCATION_COL_NAME]
    cell = ws.cell(row=excel_row, column=location_col_idx)
    cell.value = None if pd.isna(loc_value) else loc_value

# 5d. 若「地点」列为新建，将原黄色标记扩展到新列单元格
#     （原黄色标记已在整行其他列存在，新列单元格需补色）
yellow_mask = build_parking_yellow_mask(parking_df)
yellow_indices = set(yellow_mask[yellow_mask].index) if yellow_mask is not None else set()
for df_idx in yellow_indices:
    excel_row = df_idx + 2
    ws.cell(row=excel_row, column=location_col_idx).fill = YELLOW_FILL

wb.save(excel_path)
wb.close()
```

要点：
- **不删除行、不重写整表**：`ws.delete_rows()` 和 `df.to_excel()` 均不使用
- **按列名精准定位**：按表头值找「地点」列，与列位置无关
- **只有「地点」单元格被写入**：其他列、其他 sheet 完全不变
- **已有非「无」地点值已由 extract_locations 保护**：该函数第 280-286 行已有 `already_set` 跳过逻辑
- **边界处理**：若「地点」列尚不存在（旧版文件）则新建；新建时将原黄色标记行扩展到新列

### Step 2：确认 `extract_locations` 自身已保证不过覆盖

验证 `core/location.py:extract_locations()` 第 277-286 行：

```python
if "地点" not in df.columns:
    df["地点"] = "无"

already_set = (
    df["地点"].notna() & (df["地点"] != "无") & (df["地点"] != "")
)
preserved_count = already_set.sum()
```

该逻辑在 API 调用前标记已有值，后续 `still_empty` 排除它们，再写入时不会覆盖。`re_extract_locations` 调用 `extract_locations` 已继承此保护。

### Step 3：添加测试

新增 `tests/test_excel_format_preserve.py`，测试原地更新后：

1. **`test_other_sheet_format_preserved`**：多 sheet Excel 中，「财付通交易汇总」的隐藏列、冻结窗格、数据在 re-extract 后保持不变。

2. **`test_only_location_column_modified`**（核心）：「停车缴费」sheet 中，原地更新后验证：
   - 「地点」列的值已更新
   - 其他列（如「车牌」「金额」「备注2」）的单元格值**完全不变**
   - 已有非「无」地点值未被覆盖

3. **`test_new_location_column_added`**（边界）：构造不含「地点」列的旧版停车缴费 sheet，验证新列表头和数据正确写入，其他列不变。

4. **`test_missing_parking_sheet`**：文件不含「停车缴费」sheet 时返回 error JSON。

5. **`test_yellow_fill_extended_to_new_column`**：当「地点」列为新建时，已有黄色标记的行在新列上也应有黄色填充。

## 架构影响

无。输入输出签名不变，前端无感知。

## 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| 表头名不是精确"地点"（如"地点1"） | 新建重复列 | 按表头精确匹配，`extract_locations` 返回的列名也是"地点" |
| parking_df 行序与原 sheet 行序不一致 | 地点写到错误行 | `pd.read_excel` → `extract_locations` → 写回，索引对齐；原始文件也是从 `pd.read_excel` 读出的，行序一致 |
| 原地修改中途崩溃导致文件损坏 | 文件不可用 | 保留现有 try/except，异常时返回 error JSON，不损坏原文件 |
| 新建「地点」列后原黄色行新列无黄底 | 视觉不一致 | 步骤 5d 将黄色扩展到新列 |

## 测试策略

- 用 `pd.ExcelWriter` 构造含多 sheet + 格式的 Excel 文件作为 fixture
- 用 openpyxl 原地更新 + 手动构造的 parking_df（模拟 extract_locations 输出）
- 用 openpyxl 重新打开验证：其他 sheet 格式、本 sheet 非地点列数据、标黄状态
- 不依赖 DeepSeek API

## 考虑的替代方案

1. ~~删除行+全量重写~~：破坏行级样式，被否决。
2. **按列原地更新（选定）**：只操作「地点」列单元格，最小侵入。
3. 重写后格式化所有 sheet：仍需重写全表，且 col_width 被重新计算。

## 决策一致性

- 符合 ADR-003（Excel 为主要交付格式，修改时注意保留工作簿格式）
- 符合架构约束「小规模变更、局部化变更」

## 预估范围

- 修改文件：1 个源文件（`bridge.py` 约 30 行替换）+ 1 个新增测试文件
- 新增代码：约 90 行
