"""
疑似麻友识别模块

功能：
  detect_mahjong_records(df, config) → 识别潜在麻将朋友
  load_mahjong_config(config_path) → 加载配置文件

识别规则（所有条件必须同时满足）：
  1. 交易发生在晚上 20:00 ~ 次日 06:00（晚间+凌晨）
  2. "交易用途类型" == "转账"（精确匹配）
  3. "备注1" == "微信红包" 或 "微信转账"（精确匹配）
  4. "对手侧账户名称"为自然人（不含商户关键词）
  5. 同一晚间 session 内，发送方与 2-10 个不同对手方交易
  6. 同一对手方在 ≥2 个不同晚间出现 → 标记为"疑似麻友"

输出两个 DataFrame:
  - 交易明细：所有涉及疑似麻友的交易记录 + 辅助列（_对手方出现天数、_嫌疑等级）
  - 统计汇总：嫌疑人、出现天数、交易笔数、涉及金额、最高单笔金额
"""

import logging
from collections import defaultdict

import pandas as pd

from utils.columns import find_column
from utils.time_utils import time_to_minutes

logger = logging.getLogger("TenpayMerge")


# ══════════════════════════════════════════════════════════════════════════════
# 配置加载
# ══════════════════════════════════════════════════════════════════════════════

def load_mahjong_config(config_path: str | None = None) -> dict:
    """
    加载疑似麻友识别配置文件。

    Args:
        config_path: 配置文件路径，默认 scripts/config/mahjong_config.json

    Returns:
        配置字典
    """
    if config_path is not None:
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    from utils.config_loader import load_json_config
    return load_json_config("mahjong_config", {
        "商户排除关键词": [
            "公司", "店", "商行", "超市", "便利店", "百货", "餐饮",
            "酒楼", "饭店", "小吃", "奶茶", "咖啡", "烘焙", "蛋糕",
            "酒店", "宾馆", "旅馆", "民宿", "物业", "管理处",
            "药房", "医院", "诊所", "口腔", "美容", "美发",
            "汽修", "洗车", "加油站", "驾校",
            "培训", "教育", "学校", "幼儿园", "托管",
            "KTV", "网吧", "酒吧", "会所",
            "摊", "档", "铺", "行", "厂",
            "科技", "贸易", "网络", "信息", "服务", "管理",
            "有限", "责任", "合伙", "个体",
            "政府", "局", "委", "办事处", "社区",
        ],
        "单晚最少对手方数": 2,
        "单晚最多对手方数": 10,
        "最少出现天数": 2,
        "备注1匹配": ["微信红包", "微信转账"],
        "交易用途类型匹配": ["转账"],
    })


# ══════════════════════════════════════════════════════════════════════════════
# 内部工具函数
# ══════════════════════════════════════════════════════════════════════════════

def _get_suspect_level(day_count: int) -> str:
    """根据出现天数返回嫌疑等级字符串。"""
    if day_count >= 5:
        return "高"
    elif day_count >= 3:
        return "中"
    else:
        return "低"


# ══════════════════════════════════════════════════════════════════════════════
# 核心识别函数
# ══════════════════════════════════════════════════════════════════════════════

def detect_mahjong_records(
    df: pd.DataFrame,
    config: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    从去重后的交易流水中识别疑似麻友记录。

    算法流程:
      1. 基础筛选（晚间时段 + 转账 + 微信红包/转账 + 自然人）
      2. 计算 session_date（凌晨归前一日）
      3. 按 (用户, session_date) 分组，筛选满足对手方数量的 session
      4. 跨日期统计对手方出现天数
      5. 构建输出

    Args:
        df: 去重后的完整 DataFrame
        config: 配置字典，None 时自动加载

    Returns:
        (suspect_tx_df, stats_df)
        - suspect_tx_df: 涉及疑似麻友的全部交易记录（原始列 + _对手方出现天数 + _嫌疑等级）
        - stats_df: 统计汇总表
          列: 嫌疑人(对手侧账户名称), 关联用户, 出现天数, 交易笔数, 涉及总金额(元), 最高单笔金额(元)
    """
    empty_pair = (pd.DataFrame(), pd.DataFrame())

    if df.empty:
        return empty_pair

    if config is None:
        config = load_mahjong_config()

    # ── 步骤 0: 自适应列名 ──
    col_purpose = find_column(df.columns, ['交易', '用途', '类型'])
    col_note1 = find_column(df.columns, ['备注1'])
    col_opponent = find_column(df.columns, ['对手', '账户', '名称'])
    col_user = find_column(df.columns, ['用户', '账号', '名称'])
    # 回退：如果找不到用户侧账号名称，用用户ID
    if col_user is None:
        col_user = find_column(df.columns, ['用户ID'])
    col_date = find_column(df.columns, ['日期'])
    col_time = find_column(df.columns, ['时间'])
    col_amount = find_column(df.columns, ['交易', '金额', '元'])
    col_opponent_id = find_column(df.columns, ['对手方ID'])

    # 检查必要列
    required_cols = {
        '交易用途类型': col_purpose,
        '备注1': col_note1,
        '对手侧账户名称': col_opponent,
        '日期': col_date,
        '时间': col_time,
    }
    missing = [name for name, col in required_cols.items() if col is None]
    if missing:
        logger.warning(f"疑似麻友识别: 缺少必要列 {missing}，跳过")
        return empty_pair

    # ── 读取配置 ──
    merchant_kw = config.get('商户排除关键词', [])
    purpose_match = config.get('交易用途类型匹配', ['转账'])
    note1_match = config.get('备注1匹配', ['微信红包', '微信转账'])
    min_opponents = config.get('单晚最少对手方数', 2)
    max_opponents = config.get('单晚最多对手方数', 10)
    min_days = config.get('最少出现天数', 2)

    # ── 步骤 1: 基础条件筛选（向量化）──
    mask = pd.Series(True, index=df.index)

    # 1.1 交易用途类型 == "转账"（精确匹配，用 isin 防空格干扰）
    purpose_series = df[col_purpose].astype(str).str.strip()
    mask_purpose = purpose_series.isin(purpose_match)
    mask = mask & mask_purpose
    logger.debug(f"疑似麻友 - 交易用途类型筛选后: {mask.sum()} / {len(df)}")

    # 1.2 备注1 == "微信红包" 或 "微信转账"（精确匹配）
    note1_series = df[col_note1].astype(str).str.strip()
    mask_note1 = note1_series.isin(note1_match)
    mask = mask & mask_note1
    logger.debug(f"疑似麻友 - 备注1筛选后: {mask.sum()} / {len(df)}")

    # 1.3 对手侧账户名称 不含商户关键词（自然人判断）
    opponent_series = df[col_opponent].astype(str)
    mask_natural = pd.Series(True, index=df.index)
    for kw in merchant_kw:
        mask_natural = mask_natural & ~opponent_series.str.contains(kw, na=False)
    mask = mask & mask_natural
    logger.debug(f"疑似麻友 - 自然人筛选后: {mask.sum()} / {len(df)}")

    # 1.4 晚间时段过滤（时间 20:00 ~ 次日 06:00）
    # 优先用"时段"列做快速预过滤
    col_period = '时段' if '时段' in df.columns else None
    if col_period:
        mask_evening_quick = df[col_period].isin(['晚上', '凌晨'])
        # 快速路径：时段列已排除早/中/下午，但晚上含19:00-20:00的1小时
        # 仍需精确时间判断，但可以先用快速过滤减少计算
        candidate_indices = df.index[mask & mask_evening_quick]
    else:
        candidate_indices = df.index[mask]

    # 精确时间过滤：分钟数 >= 1200 (20:00) 或 < 360 (06:00)
    time_minutes = df.loc[candidate_indices, col_time].apply(time_to_minutes)
    valid_time = (time_minutes >= 1200) | ((time_minutes >= 0) & (time_minutes < 360))
    valid_time_indices = valid_time[valid_time].index

    # 合并时间过滤结果
    mask_time = pd.Series(False, index=df.index)
    mask_time.loc[valid_time_indices] = True
    mask = mask & mask_time
    logger.debug(f"疑似麻友 - 时段筛选后: {mask.sum()} / {len(df)}")

    if mask.sum() == 0:
        logger.info("疑似麻友识别: 无满足基础条件的交易记录")
        return empty_pair

    # ── 步骤 2: 计算 session_date ──
    df_candidate = df[mask].copy()

    # 解析日期
    date_parsed = pd.to_datetime(df_candidate[col_date], errors='coerce')
    if date_parsed.isna().any():
        logger.warning(f"疑似麻友识别: {date_parsed.isna().sum()} 条日期解析失败，已排除")
        valid_date_mask = date_parsed.notna()
        df_candidate = df_candidate[valid_date_mask].copy()
        date_parsed = date_parsed[valid_date_mask]
        if df_candidate.empty:
            return empty_pair

    # 解析小时数（用于判断是否跨日）
    hours = df_candidate[col_time].astype(str).str.extract(r'^(\d{1,2}):', expand=False)
    hours = pd.to_numeric(hours, errors='coerce').fillna(-1).astype(int)

    # 凌晨 (0-5点) → 归属前一日
    session_date = date_parsed.where(hours >= 6, date_parsed - pd.Timedelta(days=1))

    df_candidate['_session_date'] = session_date
    user_col_actual = col_user if col_user else col_opponent
    df_candidate['_user_name'] = df_candidate[user_col_actual].astype(str)

    # ── 步骤 3: 按 (用户, session_date) 分组，筛选有效晚间 session ──
    session_groups = df_candidate.groupby(['_user_name', '_session_date'])

    # 记录每个有效 session 的对手方集合
    valid_sessions: list[tuple[str, pd.Timestamp, set[str]]] = []
    for (user, s_date), group in session_groups:
        opponents = set(group[col_opponent].astype(str).unique())
        n_opponents = len(opponents)
        if min_opponents <= n_opponents <= max_opponents:
            valid_sessions.append((str(user), s_date, opponents))

    if not valid_sessions:
        logger.info("疑似麻友识别: 无满足对手方数量条件(2-10人)的晚间 session")
        return empty_pair

    logger.debug(f"疑似麻友 - 有效晚间 session 数: {len(valid_sessions)}")

    # ── 步骤 4: 跨日期统计对手方出现天数 ──
    pair_sessions: dict[tuple[str, str], set[pd.Timestamp]] = defaultdict(set)
    for user, s_date, opponents in valid_sessions:
        for opp in opponents:
            pair_sessions[(user, opp)].add(s_date)

    # 筛选出现天数 >= min_days 的
    suspects: dict[tuple[str, str], int] = {}
    for (user, opp), dates in pair_sessions.items():
        n_days = len(dates)
        if n_days >= min_days:
            suspects[(user, opp)] = n_days

    if not suspects:
        logger.info("疑似麻友识别: 无跨日期满足出现天数条件的对手方")
        return empty_pair

    logger.info(f"疑似麻友 - 识别到 {len(suspects)} 对 (用户, 对手方) 疑似关系")

    # ── 步骤 5: 构建输出 ──
    # 收集嫌疑人对手方名称集合
    suspect_opponents = {opp for (_, opp) in suspects}

    # 从 df_candidate 中筛选涉及嫌疑人的交易
    suspect_mask = df_candidate[col_opponent].astype(str).isin(suspect_opponents)
    suspect_tx = df_candidate[suspect_mask].copy()

    # 添加出现天数列
    def _lookup_day_count(row):
        user = str(row.get('_user_name', ''))
        opp = str(row.get(col_opponent, ''))
        return suspects.get((user, opp), 0)

    suspect_tx['_对手方出现天数'] = suspect_tx.apply(_lookup_day_count, axis=1)
    suspect_tx['_嫌疑等级'] = suspect_tx['_对手方出现天数'].apply(_get_suspect_level)

    # ── 步骤 6: 构建统计表 ──
    stats_records = []
    for (user, opp), day_count in sorted(suspects.items(), key=lambda x: -x[1]):
        opp_tx = suspect_tx[
            (suspect_tx[col_opponent].astype(str) == opp) &
            (suspect_tx['_user_name'].astype(str) == user)
        ]
        if opp_tx.empty:
            continue

        total_amount = pd.to_numeric(opp_tx[col_amount], errors='coerce').sum()
        max_amount = pd.to_numeric(opp_tx[col_amount], errors='coerce').max()
        tx_count = len(opp_tx)

        # 取对手方ID（同一对手方名称对应唯一ID，取第一个非空值）
        opponent_id = ''
        if col_opponent_id and col_opponent_id in opp_tx.columns:
            id_series = opp_tx[col_opponent_id].astype(str).str.strip()
            id_valid = id_series[id_series != '']
            if not id_valid.empty:
                opponent_id = id_valid.iloc[0]

        stats_records.append({
            '用户侧账号名称': user,
            '对手方ID': opponent_id,
            '对手侧账户名称': opp,
            '出现天数': day_count,
            '嫌疑等级': _get_suspect_level(day_count),
            '交易笔数': tx_count,
            '涉及总金额(元)': round(float(total_amount), 2) if pd.notna(total_amount) else 0.0,
            '最高单笔金额(元)': round(float(max_amount), 2) if pd.notna(max_amount) else 0.0,
        })

    stats_df = pd.DataFrame(stats_records)

    # ── 步骤 7: 清理输出列 ──
    # 只保留原始列 + _对手方出现天数 + _嫌疑等级，移除内部中间列
    output_cols = []
    for c in suspect_tx.columns:
        if c in ('_对手方出现天数', '_嫌疑等级'):
            output_cols.append(c)
        elif c in df.columns:
            output_cols.append(c)
        # 跳过 _session_date, _user_name 等内部列

    suspect_tx = suspect_tx[output_cols]

    logger.info(
        f"疑似麻友识别完成: {len(stats_df)} 名嫌疑人, "
        f"涉及 {len(suspect_tx)} 条交易记录"
    )

    return suspect_tx, stats_df
