"""
Excel 输出模块
"""

import logging
import os
import pandas as pd
from datetime import datetime
from openpyxl.styles import PatternFill
from .processor import find_column

logger = logging.getLogger("TenpayMerge")

# 黄色填充（用于标记不确定的行）
YELLOW_FILL = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")

# 默认隐藏的列（关键词匹配，所有关键词必须同时出现）
HIDDEN_COLUMN_KEYWORDS = [
    ['交易单号'],
    ['大单号'],
    ['借贷', '类型'],
    ['账户余额(元)'],
    ['交易', '业务', '类型'],
    ['用户', '银行卡号'],
    ['用户', '网银联单号'],
    ['网联', '银联'],
    ['第三方账户名称'],
    ['对手方', '银行卡号'],
    ['对手', '银行', '名称'],
    ['对手', '网银联单号'],
    ['基金公司', '信息'],
    ['间联', '非间联'],
    ['对手方', '接收', '时间'],
]

# 固定列宽的列：{关键词元组: 宽度}
FIXED_WIDTH_COLUMNS = {
    ('用户ID',): 7,
    ('对手方ID',): 7,
    ('用户侧账号名称',):8,
    ('交易用途类型',):5,
    ('备注1',):9,
    ('对手方接收金额(元)',):8,
}


def _format_worksheet(
    worksheet,
    df: pd.DataFrame,
    mark_yellow_col: str | None = None,
    mark_yellow_condition_col: str | None = None,
):
    """
    对工作表应用统一格式：列宽自适应、固定列宽、隐藏列、冻结表头、可选的黄色标记。

    Args:
        worksheet: openpyxl Worksheet 对象
        df: 对应的 DataFrame
        mark_yellow_col: 如果提供，该列值为"无"的行整行标黄
        mark_yellow_condition_col: 额外条件列，仅当该列值为"是"时才标黄
                                   （用于"车牌=无 且 备注含省份简称"的场景）
    """
    # 调整列宽（自适应）
    for column in worksheet.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                val = str(cell.value) if cell.value is not None else ''
                # 中文字符按2个字符宽度计算
                char_len = sum(2 if '一' <= c <= '鿿' or '　' <= c <= '〿' else 1 for c in val)
                if char_len > max_length:
                    max_length = char_len
            except Exception:
                pass
        adjusted_width = min(max_length + 2, 60)
        worksheet.column_dimensions[column_letter].width = max(adjusted_width, 8)

    # 应用固定列宽（覆盖自适应结果）
    for col_idx, col_name in enumerate(df.columns, 1):
        column_letter = worksheet.cell(row=1, column=col_idx).column_letter
        col_str = str(col_name)
        for keywords, width in FIXED_WIDTH_COLUMNS.items():
            if all(k in col_str for k in keywords):
                worksheet.column_dimensions[column_letter].width = width
                break

    # 隐藏指定列
    for col_idx, col_name in enumerate(df.columns, 1):
        column_letter = worksheet.cell(row=1, column=col_idx).column_letter
        col_str = str(col_name)
        for keywords in HIDDEN_COLUMN_KEYWORDS:
            if all(k in col_str for k in keywords):
                worksheet.column_dimensions[column_letter].hidden = True
                break

    # 冻结表头行
    worksheet.freeze_panes = 'A2'

    # 黄色标记：主标记列值为"无"的行（可选配合条件列）
    if mark_yellow_col and mark_yellow_col in df.columns:
        col_idx = list(df.columns).index(mark_yellow_col) + 1  # 1-based
        cond_col_idx = None
        if mark_yellow_condition_col and mark_yellow_condition_col in df.columns:
            cond_col_idx = list(df.columns).index(mark_yellow_condition_col) + 1

        for row_idx in range(2, worksheet.max_row + 1):  # 跳过表头
            cell = worksheet.cell(row=row_idx, column=col_idx)
            if str(cell.value).strip() == "无":
                # 如果有额外条件列，必须同时满足条件列值为"是"
                if cond_col_idx is not None:
                    cond_val = str(worksheet.cell(row=row_idx, column=cond_col_idx).value).strip()
                    if cond_val != "是":
                        continue
                for c in range(1, worksheet.max_column + 1):
                    worksheet.cell(row=row_idx, column=c).fill = YELLOW_FILL

    # 隐藏辅助列（以 _ 开头的内部列）
    for col_idx, col_name in enumerate(df.columns, 1):
        col_str = str(col_name)
        if col_str.startswith('_'):
            column_letter = worksheet.cell(row=1, column=col_idx).column_letter
            worksheet.column_dimensions[column_letter].hidden = True


def write_excel(
    df: pd.DataFrame,
    output_path: str,
    sheet_name: str = "财付通交易汇总",
    parking_df: pd.DataFrame | None = None,
    special_df: pd.DataFrame | None = None,
) -> str:
    """
    将 DataFrame 写入 Excel 文件，自动调整列宽。

    Args:
        df: 待输出的主 DataFrame
        output_path: 输出文件路径（含 .xlsx 扩展名）
        sheet_name: 主工作表名称
        parking_df: 可选的停车缴费 DataFrame，写入独立工作表「停车缴费」
        special_df: 可选的特殊交易 DataFrame，写入独立工作表「特殊交易」

    Returns:
        输出文件路径
    """
    if df.empty:
        logger.warning("DataFrame 为空，不生成输出")
        return ""

    # 确保输出目录存在
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    try:
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 写入主数据表
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            main_ws = writer.sheets[sheet_name]
            _format_worksheet(main_ws, df)

            # 写入停车缴费工作表
            if parking_df is not None and not parking_df.empty:
                parking_sheet_name = "停车缴费"
                parking_df.to_excel(writer, index=False, sheet_name=parking_sheet_name)
                parking_ws = writer.sheets[parking_sheet_name]
                # 对"车牌"列为"无" 且 备注含省份简称 的行标黄（提示人工复核）
                _format_worksheet(parking_ws, parking_df, mark_yellow_col="车牌", mark_yellow_condition_col="_备注含省份简称")
                logger.info(f"停车缴费工作表已输出: {len(parking_df)} 条记录")

            # 写入特殊交易工作表
            if special_df is not None and not special_df.empty:
                special_sheet_name = "特殊交易"
                special_df.to_excel(writer, index=False, sheet_name=special_sheet_name)
                special_ws = writer.sheets[special_sheet_name]
                _format_worksheet(special_ws, special_df)
                logger.info(f"特殊交易工作表已输出: {len(special_df)} 条记录")

        logger.info(f"Excel 输出完成: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Excel 输出失败: {e}")
        # fallback: 输出 CSV
        csv_path = output_path.replace('.xlsx', '.csv')
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        logger.info(f"已输出 CSV 备选: {csv_path}")
        return csv_path
