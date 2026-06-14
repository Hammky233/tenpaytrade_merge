"""
群红包识别模块

功能：
  detect_group_red_packet_records(df) → 识别群红包交易记录

识别规则（所有条件必须同时满足）：
  1. "备注1" == "微信红包"（精确匹配）
  2. "出账金额" > 0（只取支出记录）
  3. 同一"日期 + 时间"有 2 条及以上记录（群红包特征：同一时刻多人收款）
  4. "对手方接收金额(元)" < "出账金额"（排除 1对1 红包）

输出两个 DataFrame:
  - 群红包记录：满足条件的交易明细（原始列）
  - 群红包统计：按对手方汇总，包含收款次数、接收金额累计，按累计金额倒序排列
"""

import logging

import pandas as pd

from utils.columns import find_column

logger = logging.getLogger("TenpayMerge")


# ══════════════════════════════════════════════════════════════════════════════
# 核心识别函数
# ══════════════════════════════════════════════════════════════════════════════

def detect_group_red_packet_records(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """从去重后的交易流水中识别群红包记录。"""
    empty_pair = (pd.DataFrame(), pd.DataFrame())

    if df.empty:
        return empty_pair

    # ── 步骤 0: 自适应列名 ──
    col_note1 = find_column(df.columns, ['备注1'])
    col_expense = find_column(df.columns, ['出账', '金额'])
    if col_expense is None and '出账金额' in df.columns:
        col_expense = '出账金额'
    col_date = find_column(df.columns, ['日期'])
    col_time = find_column(df.columns, ['时间'])
    col_opponent_amount = find_column(df.columns, ['对手', '接收', '金额', '元'])
    col_user_name = find_column(df.columns, ['用户', '账号', '名称'])
    col_opponent_id = find_column(df.columns, ['对手方ID'])
    col_opponent_name = find_column(df.columns, ['对手', '账户', '名称'])

    required_cols = {
        '备注1': col_note1,
        '出账金额': col_expense,
        '日期': col_date,
        '时间': col_time,
        '对手方接收金额(元)': col_opponent_amount,
        '用户侧账号名称': col_user_name,
        '对手侧账户名称': col_opponent_name,
    }
    missing = [name for name, col in required_cols.items() if col is None]
    if missing:
        logger.warning(f"群红包识别: 缺少必要列 {missing}，跳过")
        return empty_pair

    # ── 步骤 1: 三条件过滤（向量化）──
    # 1.1 备注1 == "微信红包"
    note1_series = df[col_note1].astype(str).str.strip()
    mask = note1_series == '微信红包'

    # 1.2 出账金额 > 0
    expense_numeric = pd.to_numeric(df[col_expense], errors='coerce')
    mask = mask & (expense_numeric > 0)

    # 1.3 对手方接收金额 < 出账金额
    opponent_amount_numeric = pd.to_numeric(df[col_opponent_amount], errors='coerce')
    mask = mask & (opponent_amount_numeric < expense_numeric)

    if mask.sum() == 0:
        logger.info("群红包识别: 无满足基础条件的交易记录")
        return empty_pair

    df_candidate = df[mask].copy()

    # ── 步骤 2: 时间戳聚类（同一日期+时间有 2 条以上）──
    date_str = df_candidate[col_date].astype(str).str.strip()
    time_str = df_candidate[col_time].astype(str).str.strip()
    df_candidate['_ts_key'] = date_str + '|' + time_str

    group_sizes = df_candidate.groupby('_ts_key').transform('size')
    df_result = df_candidate[group_sizes >= 2].copy()

    if df_result.empty:
        logger.info("群红包识别: 无满足时间戳聚类条件(同日同时≥2条)的交易记录")
        return empty_pair

    # ── 步骤 3: 构建统计表 ──
    has_opp_id = col_opponent_id is not None and col_opponent_id in df_result.columns

    if has_opp_id:
        group_cols = [col_user_name, col_opponent_id, col_opponent_name]
    else:
        group_cols = [col_user_name, col_opponent_name]

    # 聚合统计
    stats_df = (
        df_result
        .groupby(group_cols, dropna=False)
        .agg(
            对手方收款次数=(col_opponent_name, 'count'),
            对手方接收金额元累计=(col_opponent_amount,
                           lambda x: round(pd.to_numeric(x, errors='coerce').sum(), 2)),
        )
        .reset_index()
        .sort_values('对手方接收金额元累计', ascending=False)
    )

    # 重命名为最终输出列名
    rename_map = {
        col_user_name: '用户侧账号名称',
        col_opponent_name: '对手侧账户名称',
    }
    if has_opp_id:
        rename_map[col_opponent_id] = '对手方ID'
        stats_df = stats_df[[col_user_name, col_opponent_id, col_opponent_name,
                             '对手方收款次数', '对手方接收金额元累计']]
    else:
        stats_df.insert(1, '对手方ID', '')
    stats_df.rename(columns=rename_map, inplace=True)

    # ── 步骤 4: 清理输出列（仅保留原始列）──
    output_cols = [c for c in df_result.columns if c in df.columns]
    df_result = df_result[output_cols]

    logger.info(
        f"群红包识别完成: {len(df_result)} 条群红包记录, "
        f"涉及 {len(stats_df)} 个对手方"
    )

    return df_result, stats_df
