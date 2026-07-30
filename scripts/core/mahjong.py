"""
疑似麻友识别模块

功能：
  detect_mahjong_records(df, config) → 识别潜在麻将朋友和固定交易圈子
  load_mahjong_config(config_path) → 加载配置文件

识别规则（所有条件必须同时满足）：
  1. 交易发生在配置的疑似麻友分析时段内（默认 20:00 ~ 次日 02:00）
  2. "交易用途类型" == "转账"（精确匹配）
  3. "备注1" == "微信红包" 或 "微信转账"（精确匹配）
  4. "对手侧账户名称"为自然人（不含商户关键词）
  5. 同一晚间 session 内，发送方与配置范围内数量的不同对手方交易
  6. 同一晚间 session 内至少配置数量的跨夜重复对手方共同出现

输出三个 DataFrame:
  - 交易明细：疑似麻友交易记录 + 辅助列
  - 对手方统计：按用户和对手方汇总
  - 圈子统计：按用户和共同出现的核心对手方组合汇总
"""

import logging
from collections import defaultdict

import pandas as pd

from utils.columns import find_column
from utils.time_utils import time_to_minutes

logger = logging.getLogger("TenpayMerge")


def _default_mahjong_config() -> dict:
    """返回疑似麻友识别默认配置。"""
    return {
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
        "圈子最少对手方数": 2,
        "最少出现天数": 2,
        "分析开始时间": "20:00",
        "分析结束时间": "02:00",
        "备注1匹配": ["微信红包", "微信转账"],
        "交易用途类型匹配": ["转账"],
    }


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
    return load_json_config("mahjong_config", _default_mahjong_config())


def _get_suspect_level(day_count: int) -> str:
    """根据共同出现晚数返回嫌疑等级字符串。"""
    if day_count >= 5:
        return "高"
    if day_count >= 3:
        return "中"
    return "低"


def _time_window_mask(minutes: pd.Series, start_min: int, end_min: int) -> pd.Series:
    """判断分钟数是否落入分析时段，支持跨日窗口。"""
    valid = minutes >= 0
    if start_min <= end_min:
        return valid & (minutes >= start_min) & (minutes < end_min)
    return valid & ((minutes >= start_min) | (minutes < end_min))


def _normalize_int(value, default: int, min_value: int = 1) -> int:
    """将配置值规范为整数，失败时使用默认值。"""
    try:
        parsed = int(value)
        return parsed if parsed >= min_value else default
    except (TypeError, ValueError):
        return default


def _empty_result() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """返回空结果三元组。"""
    return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()


def detect_mahjong_records(
    df: pd.DataFrame,
    config: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    从去重后的交易流水中识别疑似麻友记录。

    算法流程:
      1. 基础筛选（分析时段 + 转账 + 微信红包/转账 + 自然人）
      2. 计算 session_date（跨日窗口内的凌晨归前一日）
      3. 按 (用户, session_date) 分组，筛选满足对手方数量的 session
      4. 找出跨夜重复对手方，并保留有多个核心对手方共同出现的 session
      5. 输出交易明细、对手方统计、圈子统计

    Args:
        df: 去重后的完整 DataFrame
        config: 配置字典，None 时自动加载

    Returns:
        (suspect_tx_df, stats_df, circle_stats_df)
    """
    if df.empty:
        return _empty_result()

    if config is None:
        config = load_mahjong_config()

    col_purpose = find_column(df.columns, ["交易", "用途", "类型"])
    col_note1 = find_column(df.columns, ["备注1"])
    col_opponent = find_column(df.columns, ["对手", "账户", "名称"])
    col_user = find_column(df.columns, ["用户", "账号", "名称"])
    if col_user is None:
        col_user = find_column(df.columns, ["用户ID"])
    col_date = find_column(df.columns, ["日期"])
    col_time = find_column(df.columns, ["时间"])
    col_amount = find_column(df.columns, ["交易", "金额", "元"])
    col_opponent_id = find_column(df.columns, ["对手方ID"])

    required_cols = {
        "交易用途类型": col_purpose,
        "备注1": col_note1,
        "对手侧账户名称": col_opponent,
        "日期": col_date,
        "时间": col_time,
    }
    missing = [name for name, col in required_cols.items() if col is None]
    if missing:
        logger.warning(f"疑似麻友识别: 缺少必要列 {missing}，跳过")
        return _empty_result()

    merchant_kw = config.get("商户排除关键词", [])
    purpose_match = config.get("交易用途类型匹配", ["转账"])
    note1_match = config.get("备注1匹配", ["微信红包", "微信转账"])
    min_opponents = _normalize_int(config.get("单晚最少对手方数", 2), 2)
    max_opponents = _normalize_int(config.get("单晚最多对手方数", 10), 10)
    min_circle_opponents = _normalize_int(config.get("圈子最少对手方数", 2), 2)
    min_days = _normalize_int(config.get("最少出现天数", 2), 2)
    if max_opponents < min_opponents:
        max_opponents = min_opponents

    start_min = time_to_minutes(str(config.get("分析开始时间", "20:00")))
    end_min = time_to_minutes(str(config.get("分析结束时间", "02:00")))
    if start_min < 0 or end_min < 0 or start_min == end_min:
        logger.warning("疑似麻友识别: 分析时段配置无效，使用默认 20:00-02:00")
        start_min = time_to_minutes("20:00")
        end_min = time_to_minutes("02:00")

    mask = pd.Series(True, index=df.index)

    purpose_series = df[col_purpose].astype(str).str.strip()
    mask = mask & purpose_series.isin(purpose_match)
    logger.debug(f"疑似麻友 - 交易用途类型筛选后: {mask.sum()} / {len(df)}")

    note1_series = df[col_note1].astype(str).str.strip()
    mask = mask & note1_series.isin(note1_match)
    logger.debug(f"疑似麻友 - 备注1筛选后: {mask.sum()} / {len(df)}")

    opponent_series = df[col_opponent].astype(str)
    mask_natural = pd.Series(True, index=df.index)
    for kw in merchant_kw:
        mask_natural = mask_natural & ~opponent_series.str.contains(str(kw), na=False)
    mask = mask & mask_natural
    logger.debug(f"疑似麻友 - 自然人筛选后: {mask.sum()} / {len(df)}")

    candidate_indices = df.index[mask]
    time_minutes = df.loc[candidate_indices, col_time].apply(time_to_minutes)
    valid_time = _time_window_mask(time_minutes, start_min, end_min)
    mask_time = pd.Series(False, index=df.index)
    mask_time.loc[valid_time[valid_time].index] = True
    mask = mask & mask_time
    logger.debug(f"疑似麻友 - 分析时段筛选后: {mask.sum()} / {len(df)}")

    if mask.sum() == 0:
        logger.info("疑似麻友识别: 无满足基础条件的交易记录")
        return _empty_result()

    df_candidate = df[mask].copy()

    date_parsed = pd.to_datetime(df_candidate[col_date], errors="coerce")
    if date_parsed.isna().any():
        logger.warning(f"疑似麻友识别: {date_parsed.isna().sum()} 条日期解析失败，已排除")
        valid_date_mask = date_parsed.notna()
        df_candidate = df_candidate[valid_date_mask].copy()
        date_parsed = date_parsed[valid_date_mask]
        if df_candidate.empty:
            return _empty_result()

    candidate_minutes = df_candidate[col_time].apply(time_to_minutes)
    if start_min > end_min:
        session_date = date_parsed.where(
            candidate_minutes >= end_min,
            date_parsed - pd.Timedelta(days=1),
        )
    else:
        session_date = date_parsed

    df_candidate["_session_date"] = session_date
    user_col_actual = col_user if col_user else col_opponent
    df_candidate["_user_name"] = df_candidate[user_col_actual].astype(str)
    df_candidate["_session_key"] = (
        df_candidate["_user_name"].astype(str)
        + "|"
        + df_candidate["_session_date"].dt.strftime("%Y-%m-%d")
    )

    valid_sessions: list[dict] = []
    for (user, s_date), group in df_candidate.groupby(["_user_name", "_session_date"]):
        opponents = set(group[col_opponent].astype(str).unique())
        n_opponents = len(opponents)
        if min_opponents <= n_opponents <= max_opponents:
            valid_sessions.append({
                "user": str(user),
                "date": s_date,
                "session_key": f"{user}|{pd.Timestamp(s_date).strftime('%Y-%m-%d')}",
                "opponents": opponents,
            })

    if not valid_sessions:
        logger.info(
            f"疑似麻友识别: 无满足对手方数量条件({min_opponents}-{max_opponents}人)的晚间 session"
        )
        return _empty_result()

    pair_sessions: dict[tuple[str, str], set[pd.Timestamp]] = defaultdict(set)
    for session in valid_sessions:
        for opp in session["opponents"]:
            pair_sessions[(session["user"], opp)].add(session["date"])

    core_pairs: dict[tuple[str, str], int] = {
        pair: len(dates)
        for pair, dates in pair_sessions.items()
        if len(dates) >= min_days
    }
    if not core_pairs:
        logger.info("疑似麻友识别: 无跨日期满足出现天数条件的对手方")
        return _empty_result()

    suspect_sessions: dict[str, set[str]] = {}
    for session in valid_sessions:
        core_opponents = {
            opp for opp in session["opponents"]
            if (session["user"], opp) in core_pairs
        }
        if len(core_opponents) >= min_circle_opponents:
            suspect_sessions[session["session_key"]] = core_opponents

    if not suspect_sessions:
        logger.info("疑似麻友识别: 无满足固定圈子条件的晚间 session")
        return _empty_result()

    pair_co_sessions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for session in valid_sessions:
        session_key = session["session_key"]
        if session_key not in suspect_sessions:
            continue
        for opp in suspect_sessions[session_key]:
            pair_co_sessions[(session["user"], opp)].add(session_key)

    suspects = {
        pair: core_pairs[pair]
        for pair, sessions in pair_co_sessions.items()
        if len(sessions) >= min_days
    }
    if not suspects:
        logger.info("疑似麻友识别: 无满足共同出现晚数条件的对手方")
        return _empty_result()

    logger.info(f"疑似麻友 - 识别到 {len(suspects)} 对 (用户, 对手方) 疑似关系")

    suspect_pairs = set(suspects.keys())
    suspect_mask = (
        df_candidate["_session_key"].isin(suspect_sessions.keys())
        & df_candidate.apply(
            lambda row: (str(row.get("_user_name", "")), str(row.get(col_opponent, ""))) in suspect_pairs,
            axis=1,
        )
    )
    suspect_tx = df_candidate[suspect_mask].copy()

    def _lookup_day_count(row) -> int:
        user = str(row.get("_user_name", ""))
        opp = str(row.get(col_opponent, ""))
        return suspects.get((user, opp), 0)

    def _lookup_co_nights(row) -> int:
        user = str(row.get("_user_name", ""))
        opp = str(row.get(col_opponent, ""))
        return len(pair_co_sessions.get((user, opp), set()))

    suspect_tx["_对手方出现天数"] = suspect_tx.apply(_lookup_day_count, axis=1)
    suspect_tx["_共同出现晚数"] = suspect_tx.apply(_lookup_co_nights, axis=1)
    suspect_tx["_圈子对手方数"] = suspect_tx["_session_key"].map(
        lambda key: len(suspect_sessions.get(str(key), set()))
    )
    suspect_tx["_嫌疑等级"] = suspect_tx["_共同出现晚数"].apply(_get_suspect_level)

    stats_df = _build_opponent_stats(
        suspect_tx,
        suspects,
        pair_co_sessions,
        col_opponent,
        col_amount,
        col_opponent_id,
    )
    circle_stats_df = _build_circle_stats(
        suspect_tx,
        suspect_sessions,
        min_days,
        col_opponent,
        col_amount,
    )

    output_cols = []
    for col in suspect_tx.columns:
        if col in ("_对手方出现天数", "_共同出现晚数", "_圈子对手方数", "_嫌疑等级"):
            output_cols.append(col)
        elif col in df.columns:
            output_cols.append(col)
    suspect_tx = suspect_tx[output_cols]

    logger.info(
        f"疑似麻友识别完成: {len(stats_df)} 名嫌疑人, "
        f"{len(circle_stats_df)} 个疑似圈子, 涉及 {len(suspect_tx)} 条交易记录"
    )

    return suspect_tx, stats_df, circle_stats_df


def _amount_series(df: pd.DataFrame, col_amount: str | None) -> pd.Series:
    """读取金额列；金额只用于统计，不参与命中或排除。"""
    if col_amount and col_amount in df.columns:
        return pd.to_numeric(df[col_amount], errors="coerce").fillna(0)
    return pd.Series(0.0, index=df.index)


def _build_opponent_stats(
    suspect_tx: pd.DataFrame,
    suspects: dict[tuple[str, str], int],
    pair_co_sessions: dict[tuple[str, str], set[str]],
    col_opponent: str,
    col_amount: str | None,
    col_opponent_id: str | None,
) -> pd.DataFrame:
    """构建疑似麻友对手方统计表。"""
    records = []
    for (user, opp), day_count in suspects.items():
        opp_tx = suspect_tx[
            (suspect_tx[col_opponent].astype(str) == opp)
            & (suspect_tx["_user_name"].astype(str) == user)
        ]
        if opp_tx.empty:
            continue

        amount = _amount_series(opp_tx, col_amount)
        per_night_amount = opp_tx.assign(_amount=amount).groupby("_session_key")["_amount"].sum()
        co_night_count = len(pair_co_sessions.get((user, opp), set()))

        opponent_id = ""
        if col_opponent_id and col_opponent_id in opp_tx.columns:
            id_series = opp_tx[col_opponent_id].astype(str).str.strip()
            id_valid = id_series[id_series != ""]
            if not id_valid.empty:
                opponent_id = id_valid.iloc[0]

        total_amount = amount.sum()
        max_amount = amount.max()
        max_night_amount = per_night_amount.max() if not per_night_amount.empty else 0

        records.append({
            "用户侧账号名称": user,
            "对手方ID": opponent_id,
            "对手侧账户名称": opp,
            "出现天数": day_count,
            "共同出现晚数": co_night_count,
            "嫌疑等级": _get_suspect_level(co_night_count),
            "交易笔数": len(opp_tx),
            "涉及总金额(元)": round(float(total_amount), 2),
            "最高单笔金额(元)": round(float(max_amount), 2),
            "单晚最高金额(元)": round(float(max_night_amount), 2),
            "平均每晚金额(元)": round(float(total_amount) / co_night_count, 2) if co_night_count else 0.0,
        })

    stats_df = pd.DataFrame(records)
    if stats_df.empty:
        return stats_df
    return stats_df.sort_values(
        by=["共同出现晚数", "出现天数", "交易笔数", "涉及总金额(元)"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def _build_circle_stats(
    suspect_tx: pd.DataFrame,
    suspect_sessions: dict[str, set[str]],
    min_days: int,
    col_opponent: str,
    col_amount: str | None,
) -> pd.DataFrame:
    """构建疑似麻友圈子统计表。"""
    circle_groups: dict[tuple[str, tuple[str, ...]], set[str]] = defaultdict(set)
    for session_key, core_opponents in suspect_sessions.items():
        user = session_key.split("|", 1)[0]
        circle_groups[(user, tuple(sorted(core_opponents)))].add(session_key)

    records = []
    for (user, opponents_tuple), session_keys in circle_groups.items():
        if len(session_keys) < min_days:
            continue
        circle_tx = suspect_tx[
            (suspect_tx["_user_name"].astype(str) == user)
            & suspect_tx["_session_key"].isin(session_keys)
            & suspect_tx[col_opponent].astype(str).isin(opponents_tuple)
        ]
        if circle_tx.empty:
            continue

        amount = _amount_series(circle_tx, col_amount)
        per_night_amount = circle_tx.assign(_amount=amount).groupby("_session_key")["_amount"].sum()
        dates = sorted({key.split("|", 1)[1] for key in session_keys})

        records.append({
            "用户侧账号名称": user,
            "圈子对手方数": len(opponents_tuple),
            "核心对手方": "、".join(opponents_tuple),
            "共同出现晚数": len(session_keys),
            "交易笔数": len(circle_tx),
            "涉及总金额(元)": round(float(amount.sum()), 2),
            "单晚最高金额(元)": round(float(per_night_amount.max()), 2) if not per_night_amount.empty else 0.0,
            "覆盖日期": "、".join(dates),
        })

    circle_stats_df = pd.DataFrame(records)
    if circle_stats_df.empty:
        return circle_stats_df
    return circle_stats_df.sort_values(
        by=["共同出现晚数", "圈子对手方数", "交易笔数", "涉及总金额(元)"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
