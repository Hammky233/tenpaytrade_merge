"""
特殊交易筛选模块

功能：
  detect_special_records(df, config) → 筛选情感数字、特殊日期、特殊备注记录
  load_special_filter_config(config_path) → 加载配置文件

筛选规则（满足任一即命中）：
  1. 2月14日的交易记录
  2. 交易金额（元）格式化后包含配置中的情感数字模式
  3. 备注2 包含配置中的特殊关键词

所有操作均为 pandas 向量化，支持数十万行数据量。
"""

import os
import json
import logging
import pandas as pd
from utils.columns import find_column
from utils.paths import get_config_dir

logger = logging.getLogger("TenpayMerge")


def load_special_filter_config(config_path: str | None = None) -> dict:
    """
    加载特殊交易筛选配置文件。

    Args:
        config_path: 配置文件路径，默认 scripts/config/special_filter_config.json

    Returns:
        配置字典，包含 金额模式、备注关键词、启用2月14日
    """
    if config_path is not None:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    from utils.config_loader import load_json_config
    return load_json_config("special_filter_config", {
        "金额模式": [
            "66.66", "88.88", "99.99", "666", "888", "999",
            "520", "5200", "1314", "52.00", "6666", "8888", "9999"
        ],
        "备注关键词": [
            "快乐", "喜乐", "节", "爱你", "老公", "老婆",
            "加油", "恭喜", "祝", "谢谢"
        ],
        "启用2月14日": True,
    })


def detect_special_records(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    """
    从去重后的 DataFrame 中筛选特殊交易记录。

    筛选逻辑（OR 关系，满足任一即命中）：
    1. 启用2月14日 → 日期列的 month=2, day=14
    2. 交易金额(元) 格式化字符串包含任一金额模式
    3. 备注2 包含任一特殊关键词

    Args:
        df: 去重后的完整 DataFrame
        config: 配置字典，None 时自动加载

    Returns:
        匹配的记录 DataFrame（含全部原始列），无匹配时返回空 DataFrame
    """
    if df.empty:
        return df.copy()

    if config is None:
        config = load_special_filter_config()

    mask = pd.Series(False, index=df.index)

    # === 规则 1：2月14日 ===
    if config.get("启用2月14日", True):
        col_date = find_column(df.columns, ['日期'])
        if col_date:
            try:
                # 向量化解析日期
                date_parsed = pd.to_datetime(df[col_date], errors='coerce')
                mask_date = (date_parsed.dt.month == 2) & (date_parsed.dt.day == 14)
                mask = mask | mask_date
                hit_count = mask_date.sum()
                if hit_count > 0:
                    logger.debug(f"规则1（2月14日）命中: {hit_count} 条")
            except Exception as e:
                logger.warning(f"日期解析失败，跳过2月14日规则: {e}")
        else:
            logger.debug("未找到「日期」列，跳过2月14日规则")

    # === 规则 2：交易金额含情感数字 ===
    amount_patterns = config.get("金额模式", [])
    if amount_patterns:
        col_amount = find_column(df.columns, ['交易', '金额', '元'])
        if col_amount:
            # 转为数值 → 格式化为 2 位小数字符串 → 向量化子串匹配
            amount_numeric = pd.to_numeric(df[col_amount], errors='coerce')
            amount_str = amount_numeric.apply(
                lambda x: f"{x:.2f}" if pd.notna(x) else ""
            )
            mask_amount = pd.Series(False, index=df.index)
            for pattern in amount_patterns:
                mask_amount = mask_amount | amount_str.str.contains(pattern, na=False)
            mask = mask | mask_amount
            hit_count = mask_amount.sum()
            if hit_count > 0:
                logger.debug(f"规则2（金额模式）命中: {hit_count} 条")
        else:
            logger.debug("未找到「交易金额(元)」列，跳过金额模式规则")

    # === 规则 3：备注2含特殊关键词 ===
    note_keywords = config.get("备注关键词", [])
    if note_keywords:
        col_note2 = find_column(df.columns, ['备注2'])
        if col_note2:
            mask_note = pd.Series(False, index=df.index)
            for kw in note_keywords:
                mask_note = mask_note | df[col_note2].astype(str).str.contains(kw, na=False)
            mask = mask | mask_note
            hit_count = mask_note.sum()
            if hit_count > 0:
                logger.debug(f"规则3（备注关键词）命中: {hit_count} 条")
        else:
            logger.debug("未找到「备注2」列，跳过备注关键词规则")

    result = df[mask].copy()

    logger.info(
        f"特殊交易筛选: {len(result)}/{len(df)} 条 "
        f"({len(result)/len(df)*100:.1f}%)"
    )

    return result
