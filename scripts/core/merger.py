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
    基于 8 列联合主键去重。

    去重键：用户ID + 交易单号 + 大单号 + 日期 + 时间 + 借贷类型 + 交易金额(元) + 对手方ID
    加入「对手方ID」是为了避免群红包场景误删：群发红包时多条记录的
    用户ID/交易单号/大单号/日期/时间/借贷类型/金额完全相同，仅对手方ID和对手方接收金额不同。

    Args:
        df: 输入 DataFrame

    Returns:
        去重后的 DataFrame
    """
    before = len(df)
    if before == 0:
        return df

    # 8 列联合去重键（按顺序尝试定位）
    key_defs: list[tuple[list[str], str]] = [
        (['用户ID'], '用户ID'),
        (['交易单号'], '交易单号'),
        (['大单号'], '大单号'),
        (['日期'], '日期'),
        (['时间'], '时间'),
        (['借贷', '类型'], '借贷类型'),
        (['交易', '金额', '元'], '交易金额(元)'),
        (['对手方ID'], '对手方ID'),
    ]

    keys = []
    for keywords, fallback in key_defs:
        col = find_column(df.columns, keywords)
        if col is None and fallback in df.columns:
            col = fallback
        if col:
            keys.append(col)
        else:
            logger.warning(f"去重: 未找到列 {keywords}，从去重键中排除")

    if keys:
        logger.info(f"去重依据: {' + '.join(keys)}")
        df = df.drop_duplicates(subset=keys, keep='first')
    else:
        logger.warning("所有去重列不可用，fallback 到全列去重")
        df = df.drop_duplicates(keep='first')

    after = len(df)
    removed = before - after
    if removed > 0:
        logger.info(f"去重: {before} → {after} (移除 {removed} 条重复)")
    else:
        logger.info("去重: 无重复数据")

    df = df.reset_index(drop=True)
    return df
