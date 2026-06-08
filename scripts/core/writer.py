"""
Excel 输出模块
"""

import logging
import os
import pandas as pd
from datetime import datetime
from .processor import find_column

logger = logging.getLogger("TenpayMerge")

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


def write_excel(df: pd.DataFrame, output_path: str, sheet_name: str = "财付通交易汇总") -> str:
    """
    将 DataFrame 写入 Excel 文件，自动调整列宽。

    Args:
        df: 待输出的 DataFrame
        output_path: 输出文件路径（含 .xlsx 扩展名）
        sheet_name: 工作表名称

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

            # 调整列宽
            worksheet = writer.sheets[sheet_name]
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

        logger.info(f"Excel 输出完成: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Excel 输出失败: {e}")
        # fallback: 输出 CSV
        csv_path = output_path.replace('.xlsx', '.csv')
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        logger.info(f"已输出 CSV 备选: {csv_path}")
        return csv_path
