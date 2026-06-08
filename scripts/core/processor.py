"""
数据清洗模块

职责链（按调用顺序）：
  clean_columns(df)              → 列名清洗（BOM、特殊Unicode字符）
  merge_duplicate_columns(df)    → 合并重复列（向量化实现）
  convert_amounts(df)            → 自动识别"金额(分)"列，转为"金额(元)"
  split_datetime(df)             → 拆分"交易时间"列 → 日期 + 时间（插在"交易用途类型"后面）
  calc_income_expense(df)        → 根据借贷类型拆分进账金额/出账金额
"""

import logging
import re
import pandas as pd
import numpy as np

logger = logging.getLogger("TenpayMerge")


# ============================================================================
# 列名工具函数
# ============================================================================

def find_column(columns, keywords):
    """
    精准匹配列名：必须同时包含所有关键词。
    用于自适应识别腾讯返回的不固定列名。

    Args:
        columns: 列名列表（pd.Index 或 list）
        keywords: 关键词列表，所有关键词必须同时出现在列名中

    Returns:
        匹配到的列名（str）或 None
    """
    for col in columns:
        col_str = str(col)
        if all(k in col_str for k in keywords):
            return col_str
    return None


def find_columns_containing(columns, keywords):
    """
    查找所有包含指定关键词组合的列。
    用于查找多个金额列等场景。

    Args:
        columns: 列名列表
        keywords: 关键词列表，所有关键词必须同时出现在列名中

    Returns:
        匹配到的列名列表
    """
    result = []
    for col in columns:
        col_str = str(col)
        if all(k in col_str for k in keywords):
            result.append(col_str)
    return result


# ============================================================================
# 清洗函数
# ============================================================================

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    清洗列名：去除 BOM 和特殊 Unicode 控制字符，去除首尾空格。

    Args:
        df: 输入 DataFrame

    Returns:
        清洗后的 DataFrame（原地修改列名）
    """
    df.columns = df.columns.astype(str)
    df.columns = df.columns.str.strip()

    # 移除常见特殊字符
    special_chars = ['﻿', '‎', '‪', '‬', '‌', '​', '‍']
    for char in special_chars:
        df.columns = df.columns.str.replace(char, '', regex=False)

    return df


def merge_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    合并重复列：当存在同名多列时，用后续列的非空值填充第一列，再删除重复列。

    向量化实现：用 combine_first 替代逐行遍历

    Args:
        df: 输入 DataFrame

    Returns:
        处理后无重复列的 DataFrame
    """
    dup_mask = df.columns.duplicated()
    if not dup_mask.any():
        return df

    dup_names = df.columns[dup_mask].unique().tolist()
    logger.info(f"发现重复列名: {dup_names}")

    for col_name in dup_names:
        col_indices = [i for i, c in enumerate(df.columns) if c == col_name]
        if len(col_indices) < 2:
            continue

        first_idx = col_indices[0]
        # 将后续重复列的非空值合并到第一列
        for dup_idx in col_indices[1:]:
            # 用第一列的 NaN/空字符串 位置，从重复列取值填充
            first_col = df.iloc[:, first_idx]
            dup_col = df.iloc[:, dup_idx]
            # 判断第一列"空"的标准：NaN 或 空字符串
            mask_empty = first_col.isna() | (first_col == '')
            # 向量化填充
            df.iloc[mask_empty.values, first_idx] = dup_col[mask_empty].values

    # 删除重复列（保留第一个出现的）
    df = df.loc[:, ~df.columns.duplicated(keep='first')]
    logger.debug(f"合并重复列后列数: {len(df.columns)}")

    return df


def convert_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """
    自动识别所有"金额(分)"列，转换为"金额(元)"并重命名。

    同时处理不包含"(分)"但包含"金额"且列名不含"(元)"的列（如"账户余额(分)"）。

    Args:
        df: 输入 DataFrame

    Returns:
        金额转换后的 DataFrame
    """
    # 查找所有包含"分"的金额列
    amount_cols_cents = find_columns_containing(df.columns, ['金额', '分'])

    rename_map = {}

    for col in amount_cols_cents:
        if col not in df.columns:
            continue
        try:
            # 先清理数据中的特殊字符（备注列可能混入的）
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].str.replace(r'[‌‎‪‬​‍﻿]', '', regex=True)
            # 转数值并除以100
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0) / 100
            new_name = col.replace('(分)', '(元)')
            rename_map[col] = new_name
            logger.debug(f"金额转换: {col} -> {new_name}")
        except Exception as e:
            logger.warning(f"金额转换失败 [{col}]: {e}")

    # 检查是否有余额相关列（可能不含"分"）
    col_balance = find_column(df.columns, ['余额'])
    if col_balance and col_balance not in rename_map:
        try:
            df[col_balance] = df[col_balance].astype(str).str.strip()
            df[col_balance] = df[col_balance].str.replace(r'[‌‎‪‬​‍﻿]', '', regex=True)
            df[col_balance] = pd.to_numeric(df[col_balance], errors='coerce').fillna(0) / 100
            if '(分)' in col_balance:
                new_name = col_balance.replace('(分)', '(元)')
            elif '(元)' not in col_balance:
                new_name = col_balance + '(元)'
            else:
                new_name = col_balance
            rename_map[col_balance] = new_name
            logger.debug(f"余额转换: {col_balance} -> {new_name}")
        except Exception as e:
            logger.warning(f"余额转换失败 [{col_balance}]: {e}")

    if rename_map:
        df.rename(columns=rename_map, inplace=True)

    return df


def split_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """
    拆分"交易时间"列 → "日期" + "时间"

    - 用 find_column 自适应识别"交易时间"列
    - 用 find_column 找到"交易用途类型"作为锚点，将拆分结果插入其后

    Args:
        df: 输入 DataFrame

    Returns:
        拆分后的 DataFrame
    """
    col_time = find_column(df.columns, ['交易', '时间'])
    if not col_time:
        logger.warning("未找到「交易时间」列，跳过时间拆分")
        return df

    # 解析时间字符串
    time_str = df[col_time].astype(str).str.strip()
    # 移除可能混入的特殊字符
    time_str = time_str.str.replace(r'[‌‎‪‬﻿]', '', regex=True)

    split_parts = time_str.str.split(n=1, expand=True)

    date_part = split_parts[0].str.strip() if split_parts.shape[1] >= 1 else time_str
    time_part = ''
    if split_parts.shape[1] > 1:
        time_part = split_parts[1].str.strip()

    # 尝试格式化日期
    try:
        date_formatted = pd.to_datetime(date_part, errors='coerce').dt.strftime('%Y/%m/%d')
        date_formatted = date_formatted.fillna(date_part)
    except Exception:
        date_formatted = date_part

    # 删除原"交易时间"列
    df.drop(columns=[col_time], inplace=True)

    # 找到锚点列"交易用途类型"，将日期/时间插入其后
    col_purpose = find_column(df.columns, ['交易', '用途', '类型'])

    if col_purpose:
        insert_pos = df.columns.get_loc(col_purpose) + 1
    else:
        # fallback：插到交易业务类型后面
        col_biz_type = find_column(df.columns, ['交易', '业务', '类型'])
        if col_biz_type:
            insert_pos = df.columns.get_loc(col_biz_type) + 1
        else:
            insert_pos = 0  # 最后兜底：插到最前面

    # 列重排：在 insert_pos 处插入 日期、时间
    cols = df.columns.tolist()
    new_cols = cols[:insert_pos] + ['日期', '时间'] + cols[insert_pos:]
    # 赋值新列
    df['日期'] = date_formatted
    df['时间'] = time_part
    df = df[new_cols]

    logger.debug(f"时间拆分完成，日期/时间插入在位置 {insert_pos}")
    return df


def calc_income_expense(df: pd.DataFrame) -> pd.DataFrame:
    """
    根据"借贷类型"列拆分进账金额和出账金额。

    - 用 find_column 自适应识别"借贷类型"和"交易金额(元)"列
    - 进账：借贷类型包含「入」→ 进账金额 = 交易金额
    - 出账：借贷类型包含「出」→ 出账金额 = 交易金额
    - 新列追加到末尾

    Args:
        df: 输入 DataFrame

    Returns:
        添加了进账金额/出账金额的 DataFrame
    """
    col_type = find_column(df.columns, ['借贷'])
    if not col_type:
        logger.warning("未找到「借贷类型」列，跳过进账/出账拆分")
        return df

    # 查找交易金额列（已经是元）
    col_amount = find_column(df.columns, ['交易', '金额', '元'])
    if not col_amount:
        # fallback: 尝试找包含"交易金额"的列
        col_amount = find_column(df.columns, ['交易', '金额'])
    if not col_amount:
        logger.warning("未找到「交易金额(元)」列，跳过进账/出账拆分")
        return df

    type_str = df[col_type].astype(str)
    amount_numeric = pd.to_numeric(df[col_amount], errors='coerce').fillna(0)

    df['进账金额'] = 0.0
    df['出账金额'] = 0.0

    is_income = type_str.str.contains('入', na=False)
    is_expense = type_str.str.contains('出', na=False)

    df.loc[is_income, '进账金额'] = amount_numeric[is_income]
    df.loc[is_expense, '出账金额'] = amount_numeric[is_expense]

    logger.debug("进账/出账金额拆分完成")
    return df


# ============================================================================
# 主处理入口
# ============================================================================

def process_dataframe(df: pd.DataFrame) -> pd.DataFrame | None:
    """
    对单个 DataFrame 执行完整清洗流水线。

    Args:
        df: 原始 DataFrame

    Returns:
        清洗后的 DataFrame 或 None（关键字段缺失时）
    """
    try:
        # 创建独立副本，避免 SettingWithCopyWarning
        df = df.copy()

        # 1. 列名清洗
        df = clean_columns(df)

        # 2. 合并重复列
        df = merge_duplicate_columns(df)

        # 3. 关键字段验证
        col_time = find_column(df.columns, ['交易', '时间'])
        col_amount = find_column(df.columns, ['交易', '金额'])
        col_type = find_column(df.columns, ['借贷'])

        if not col_time or not col_amount or not col_type:
            logger.warning(
                f"关键字段缺失 - 时间:{col_time}, 金额:{col_amount}, 借贷类型:{col_type}"
            )
            logger.warning(f"  当前列: {list(df.columns)}")
            return None

        # 4. 金额转换（分→元）
        df = convert_amounts(df)

        # 5. 时间拆分
        df = split_datetime(df)

        # 6. 进账/出账拆分
        df = calc_income_expense(df)

        return df

    except Exception as e:
        import traceback
        logger.error(f"数据处理异常: {e}")
        logger.debug(traceback.format_exc())
        return None
