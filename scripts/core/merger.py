"""
合并 + 去重模块
"""

import logging
import pandas as pd
from utils.columns import find_column

logger = logging.getLogger("TenpayMerge")


def merge_dataframes(dfs: list[pd.DataFrame]) -> pd.DataFrame:
    """
    合并多个 DataFrame 为一个。

    处理不同 DataFrame 列不完全一致的情况：
    - 缺失列填空值
    - 额外列保留

    Args:
        dfs: DataFrame 列表

    Returns:
        合并后的 DataFrame
    """
    if not dfs:
        return pd.DataFrame()

    if len(dfs) == 1:
        return dfs[0].copy()

    # 收集所有列名（保持顺序）
    all_columns = []
    seen = set()
    for df in dfs:
        for col in df.columns:
            if col not in seen:
                all_columns.append(col)
                seen.add(col)

    # 对齐列
    aligned_dfs = []
    for df in dfs:
        df_aligned = df.reindex(columns=all_columns)
        aligned_dfs.append(df_aligned)

    merged = pd.concat(aligned_dfs, ignore_index=True)
    logger.info(f"合并: {len(dfs)} 个文件 → {len(merged)} 行, {len(merged.columns)} 列")
    return merged


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """
    基于 交易单号 + 大单号 联合主键去重。

    策略：
    1. 若两个字段覆盖率均 > 50%，按联合主键去重
    2. 若仅一个字段覆盖率 > 50%，按该字段去重
    3. 否则 fallback 到全列去重

    Args:
        df: 输入 DataFrame

    Returns:
        去重后的 DataFrame
    """
    before = len(df)
    if before == 0:
        return df

    col_trade_no = find_column(df.columns, ['交易单号'])
    col_big_order = find_column(df.columns, ['大单号'])

    keys = []
    if col_trade_no and df[col_trade_no].notna().sum() > len(df) * 0.5:
        # 确保是字符串类型以便比较
        df[col_trade_no] = df[col_trade_no].astype(str)
        keys.append(col_trade_no)
    if col_big_order and df[col_big_order].notna().sum() > len(df) * 0.5:
        df[col_big_order] = df[col_big_order].astype(str)
        keys.append(col_big_order)

    if keys:
        logger.info(f"去重依据: {' + '.join(keys)}")
        df = df.drop_duplicates(subset=keys, keep='first')
    else:
        logger.warning("交易单号和大单号覆盖率不足，fallback 到全列去重")
        df = df.drop_duplicates(keep='first')

    after = len(df)
    removed = before - after
    if removed > 0:
        logger.info(f"去重: {before} → {after} (移除 {removed} 条重复)")
    else:
        logger.info("去重: 无重复数据")

    df = df.reset_index(drop=True)
    return df
