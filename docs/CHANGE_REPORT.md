# 变更报告 — T003

## 变更的文件

| 文件 | 变更类型 |
|------|----------|
| `scripts/webui/bridge.py` | 修改 — `re_extract_locations` 写回逻辑从 pd.ExcelWriter 全重写改为 openpyxl 按列原地更新 |
| `tests/test_excel_format_preserve.py` | 新增 — 6 个测试用例 |
| `docs/CHANGE_REPORT.md` | 修改 — 本报告 |

## 变更摘要

修复 GUI「重新提取地点」功能在写回 Excel 时因全表重写破坏所有工作表格式的问题，改为 openpyxl 按列原地更新——只操作「停车缴费」sheet 的「地点」列单元格。

### 具体修改

**`scripts/webui/bridge.py`（第 526-564 行）：**

替换前（有缺陷）：
```python
# pd.ExcelWriter 创建新文件，丢弃所有已有格式
with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
    for sheet_name, sheet_df in all_sheets.items():
        sheet_df.to_excel(writer, index=False, sheet_name=sheet_name)

# 只恢复「停车缴费」一个 sheet 的格式
_sanitize_for_excel(parking_df)
wb = openpyxl.load_workbook(excel_path)
if "停车缴费" in wb.sheetnames:
    ws = wb["停车缴费"]
    _format_worksheet(ws, parking_df)
```

替换后（原地修改）：
```python
_sanitize_for_excel(parking_df)
wb = openpyxl.load_workbook(excel_path)
ws = wb["停车缴费"]

# 定位「地点」列索引（按表头名），不存在则新建
location_col_idx = None
for cell in ws[1]:
    if cell.value == "地点":
        location_col_idx = cell.column
        break
if location_col_idx is None:
    location_col_idx = (ws.max_column or 0) + 1
    ws.cell(row=1, column=location_col_idx).value = "地点"

# 逐行只更新「地点」单元格的值
for df_idx in range(len(parking_df)):
    excel_row = df_idx + 2
    loc_value = parking_df.iloc[df_idx]["地点"]
    ws.cell(row=excel_row, column=location_col_idx).value = (
        None if pd.isna(loc_value) else loc_value
    )

# 若新建列，将原黄色标记扩展到新列单元格
yellow_mask = build_parking_yellow_mask(parking_df)
if yellow_mask is not None:
    yellow_indices = set(yellow_mask[yellow_mask].index)
    for df_idx in yellow_indices:
        ws.cell(row=df_idx + 2, column=location_col_idx).fill = YELLOW_FILL

wb.save(excel_path)
wb.close()
```

关键设计：
- **不删除行、不重写整表**：`ws.delete_rows()` 和 `df.to_excel()` 均不使用
- **仅「地点」列单元格被写入**：其他列、其他 sheet 完全不受影响
- **按表头名称精准定位**：与列位置无关，只要表头名为"地点"即可
- **新建列时扩展黄色标记**：原标黄行的新「地点」列单元格补上黄色填充
- **已有非"无"地点值由 extract_locations 自身保护**，原地写入不做额外覆盖（只写 DataFrame 返回的值，extract_locations 已跳过已有值行）

### 新增测试

**`tests/test_excel_format_preserve.py`** — 6 个用例：

| 测试 | 场景 | 验证点 |
|------|------|--------|
| `test_other_sheet_format_preserved` | 多 sheet Excel，其他 sheet 的隐藏列、冻结窗格 | 对比原地更新前后，格式和数据完全一致 |
| `test_only_location_column_modified` | 「停车缴费」sheet 的非「地点」列 | 列如车牌、金额的单元格值完全不变 |
| `test_new_location_column_added` | 旧版文件没有「地点」列 | 自动新建列，表头和数据正确写入 |
| `test_missing_parking_sheet` | 文件不含「停车缴费」sheet | 返回格式正确的 error JSON |
| `test_existing_locations_preserved` | 已有非"无"地点值 | 原地更新后不被覆盖 |
| `test_yellow_fill_extended_to_new_column` | 新建「地点」列时原黄色行 | 新列单元格被正确标黄 |

## 已执行的测试

```powershell
cd /d C:\CCProject\tenpaytrade_merge
.\.venv\Scripts\python -m pytest tests/ -v
```

结果：**46 passed** in 1.15s（新增 6 个，原有 40 个无回归）。

## 已知风险

- 若用户在「停车缴费」sheet 中有自定义的行高、单元格边框等局部格式，本次修改不会破坏它们（原地修改只写「地点」列的 `value` 和 `fill`，不动其他属性）
- 当原文件不包含「地点」列时，新建列使用 Excel 默认列宽；用户可手动调整
- `extract_locations` 的保护逻辑（已有非"无"值不覆盖）保持不变

## 经验教训

1. **`pd.ExcelWriter` 创建全新文件，不是原地修改**：即使只写入相同的 sheet 和数据，格式也会全部丢失。后续 `_format_worksheet` 只能恢复列级格式，无法恢复行级样式。
2. **Excel 原地修改应精准操作目标单元格**：操作整表或整行（`delete_rows` + 重写）会破坏行级样式。正确的做法是按列名称定位目标列、只操作目标列单元格。
3. **表头名称匹配比列位置更稳健**：`for cell in ws[1]` 遍历表头行找"地点"列，与列位置无关，对列顺序变化有容错。
4. **黄色标记应该扩展到新增列**：`_format_worksheet` 在初始创建时对整行应用黄色填充，但新增列不在当时的工作表 schema 中，所以新建列需要手动补充黄色填充。
