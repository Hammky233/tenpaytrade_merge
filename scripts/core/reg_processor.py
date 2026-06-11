"""
注册信息清洗合并模块

将多个 TenpayRegInfo.txt 文件的解析结果合并为两个 DataFrame：
- 基本信息表（去重后的主记录）
- 变更记录表（注销 / 身份信息变更历史）
"""

import os
import logging
import pandas as pd

logger = logging.getLogger("TenpayMerge")

# 主记录输出列（按此顺序排列，银行账号相关列放在末尾）
PRIMARY_OUTPUT_COLUMNS = [
    '账户状态',
    '账号',
    '注册姓名',
    '注册身份证号',
    '注册时间',
    '绑定手机',
    '绑定状态',
    '开户行信息',
    '银行账号',
    '数据来源',
    '调证编号',
]

# 变更记录输出列
CHANGE_OUTPUT_COLUMNS = [
    '账号',
    '注册姓名',
    '注册身份证号',
    '注册时间',
    '注销时间',
    '变更类型',
    '当前状态',
    '当前姓名',
    '当前身份证号',
    '数据来源',
    '调证编号',
]


def _classify_change_type(primary: dict, change: dict) -> str:
    """
    根据主记录状态判断变更类型。

    - 状态=已注销 → "账户注销"
    - 状态=正常 + 注销区有数据 → "身份信息变更"
    - 其他 → "未知变更"
    """
    status = primary.get('账户状态', '').strip()
    if status == '已注销':
        return '账户注销'
    elif status == '正常':
        return '身份信息变更'
    else:
        return '未知变更'


def process_reg_data(records: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    合并所有文件的注册信息解析结果。

    Args:
        records: read_tenpay_reg_info() 返回的字典列表（已过滤 None）

    Returns:
        (basic_df, changes_df) — 基本信息表和变更记录表
    """
    if not records:
        logger.warning("无有效的注册信息记录")
        return pd.DataFrame(), pd.DataFrame()

    primary_rows = []
    change_rows = []

    for rec in records:
        primary = rec["primary"]
        source_file = rec.get("source_file", "")
        case_number = rec.get("case_number", "")

        # 主记录行
        row = {}
        for col in PRIMARY_OUTPUT_COLUMNS:
            if col == '数据来源':
                row[col] = source_file
            elif col == '调证编号':
                row[col] = case_number
            else:
                row[col] = primary.get(col, '').strip()
        primary_rows.append(row)

        # 变更记录
        for change in rec.get("changes", []):
            change_type = _classify_change_type(primary, change)
            crow = {
                '账号': change.get('账号', '').strip(),
                '注册姓名': change.get('注册姓名', '').strip(),
                '注册身份证号': change.get('注册身份证号', '').strip(),
                '注册时间': change.get('注册时间', '').strip(),
                '注销时间': change.get('注销时间', '').strip(),
                '变更类型': change_type,
                '当前状态': primary.get('账户状态', '').strip(),
                '当前姓名': primary.get('注册姓名', '').strip(),
                '当前身份证号': primary.get('注册身份证号', '').strip(),
                '数据来源': source_file,
                '调证编号': case_number,
            }
            change_rows.append(crow)

    # 构建 DataFrame
    basic_df = pd.DataFrame(primary_rows, columns=PRIMARY_OUTPUT_COLUMNS, dtype=str)
    changes_df = pd.DataFrame(change_rows, columns=CHANGE_OUTPUT_COLUMNS, dtype=str)

    logger.info(f"注册信息汇总: {len(basic_df)} 条主记录（来自 {len(records)} 个文件）")

    if not changes_df.empty:
        # 统计变更类型分布
        type_counts = changes_df['变更类型'].value_counts().to_dict()
        type_str = ', '.join(f'{k}: {v}' for k, v in type_counts.items())
        logger.info(f"变更记录: {len(changes_df)} 条（{type_str}）")

    # 去重：按 账号 + 注册身份证号 去重（保留首次出现）
    before = len(basic_df)
    if before > 0:
        dedup_cols = ['账号', '注册身份证号']
        # 确保这两个列存在
        available_keys = [c for c in dedup_cols if c in basic_df.columns]
        if available_keys:
            basic_df = basic_df.drop_duplicates(subset=available_keys, keep='first')
            after = len(basic_df)
            removed = before - after
            if removed > 0:
                logger.info(f"基本信息去重: {before} → {after} (移除 {removed} 条重复)")
            else:
                logger.info("基本信息去重: 无重复数据")

    basic_df = basic_df.reset_index(drop=True)
    changes_df = changes_df.reset_index(drop=True)

    return basic_df, changes_df


def build_person_info(basic_df: pd.DataFrame) -> pd.DataFrame:
    """
    从注册信息汇总表中提取人员基础信息（去重）。

    仅保留 注册姓名、注册身份证号、绑定手机 三个字段，
    去重后按姓名排序。排除三者全为空的行（如账号不存在/已注销且无身份信息）。

    Args:
        basic_df: process_reg_data 返回的 basic_df

    Returns:
        去重后的人员基础信息 DataFrame（列: 注册姓名, 注册身份证号, 绑定手机）
    """
    if basic_df.empty:
        return pd.DataFrame()

    person_cols = ['注册姓名', '注册身份证号', '绑定手机']
    # 只选取存在的列
    available_cols = [c for c in person_cols if c in basic_df.columns]
    if not available_cols:
        return pd.DataFrame()

    person_df = basic_df[available_cols].copy()

    # 排除三者全为空的行
    person_df = person_df.replace('', pd.NA).dropna(how='all')
    # 将 NaN 恢复为空字符串（保证 xlsx 中显示空而非 NaN）
    person_df = person_df.fillna('')

    if person_df.empty:
        return person_df

    # 去重
    before = len(person_df)
    person_df = person_df.drop_duplicates(keep='first')
    after = len(person_df)
    if before > after:
        logger.info(f"基础信息去重: {before} → {after} (移除 {before - after} 条重复)")

    # 按姓名排序
    person_df = person_df.sort_values(by='注册姓名', key=lambda s: s.str.lower()).reset_index(drop=True)

    logger.info(f"基础信息: {len(person_df)} 个自然人")
    return person_df
