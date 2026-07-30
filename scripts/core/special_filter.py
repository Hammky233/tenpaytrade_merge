"""
特殊交易筛选模块。

四类规则满足任一即命中：
  1. 每年重复的特殊日期
  2. 交易金额（元）格式化为两位小数后的字面量模式
  3. 备注2中的特殊关键词
  4. 对手侧账户名称中的特殊关键词
"""

from datetime import datetime
import json
import logging

import pandas as pd

from utils.columns import find_column

logger = logging.getLogger("TenpayMerge")


_DEFAULT_AMOUNT_PATTERNS = [
    "66.66", "88.88", "99.99", "666", "888", "999",
    "520", "5200", "1314", "52.00", "6666", "8888", "9999",
]
_DEFAULT_ATTENTION_KEYWORDS = [
    "桑拿", "足浴", "休闲", "会所", "按摩", "养生",
    "足疗", "SPA", "spa", "温泉", "酒店",
]
_DEFAULT_NOTE_KEYWORDS = [
    "快乐", "喜乐", "节", "爱你", "老公", "老婆",
    "加油", "恭喜", "祝", "谢谢",
] + _DEFAULT_ATTENTION_KEYWORDS


def default_special_filter_config() -> dict:
    """返回特殊交易筛选的新格式默认配置。"""
    return {
        "启用特殊日期": True,
        "特殊日期": ["02-14", "05-20"],
        "启用特殊金额": True,
        "金额模式": list(_DEFAULT_AMOUNT_PATTERNS),
        "启用特殊备注": True,
        "备注关键词": list(_DEFAULT_NOTE_KEYWORDS),
        "启用特殊对手方": True,
        "对手侧账户名称关键词": list(_DEFAULT_ATTENTION_KEYWORDS),
    }


def normalize_special_date(value) -> str | None:
    """将 M-D/MM-DD 规范化为 MM-DD；非法日期返回 None。"""
    text = str(value).strip()
    parts = text.split("-")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    try:
        month, day = (int(part) for part in parts)
        # 使用闰年校验，使 02-29 成为合法的年度重复日期。
        datetime(2000, month, day)
    except (TypeError, ValueError):
        return None
    return f"{month:02d}-{day:02d}"


def _normalize_string_list(value) -> list[str]:
    """清理字符串列表并按原顺序去重。"""
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def normalize_special_filter_config(config: dict | None) -> dict:
    """规范化新旧特殊交易配置，并补齐缺失字段。"""
    raw = config if isinstance(config, dict) else {}
    defaults = default_special_filter_config()

    amount_patterns = _normalize_string_list(
        raw.get("金额模式", defaults["金额模式"])
    )
    note_keywords = _normalize_string_list(
        raw.get("备注关键词", defaults["备注关键词"])
    )
    opponent_keywords = _normalize_string_list(
        raw.get("对手侧账户名称关键词", defaults["对手侧账户名称关键词"])
    )

    raw_dates = raw.get("特殊日期", defaults["特殊日期"])
    dates = []
    seen_dates = set()
    if isinstance(raw_dates, list):
        for item in raw_dates:
            normalized = normalize_special_date(item)
            if normalized and normalized not in seen_dates:
                dates.append(normalized)
                seen_dates.add(normalized)

    return {
        "启用特殊日期": bool(
            raw.get("启用特殊日期", raw.get("启用2月14日", True))
        ),
        "特殊日期": dates,
        "启用特殊金额": bool(raw.get("启用特殊金额", bool(amount_patterns))),
        "金额模式": amount_patterns,
        "启用特殊备注": bool(raw.get("启用特殊备注", bool(note_keywords))),
        "备注关键词": note_keywords,
        "启用特殊对手方": bool(raw.get("启用特殊对手方", defaults["启用特殊对手方"])),
        "对手侧账户名称关键词": opponent_keywords,
    }


def load_special_filter_config(config_path: str | None = None) -> dict:
    """从用户配置或内置默认配置中读取并规范化特殊交易配置。"""
    if config_path is not None:
        with open(config_path, "r", encoding="utf-8") as file:
            return normalize_special_filter_config(json.load(file))

    from utils.config_loader import load_json_config

    loaded = load_json_config(
        "special_filter_config", default_special_filter_config()
    )
    return normalize_special_filter_config(loaded)


def _literal_contains(series: pd.Series, patterns: list[str]) -> pd.Series:
    """对一列执行多个字面量子串的 OR 匹配。"""
    mask = pd.Series(False, index=series.index)
    text = series.fillna("").astype(str)
    for pattern in patterns:
        mask = mask | text.str.contains(pattern, na=False, regex=False)
    return mask


def detect_special_records(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    """从去重后的 DataFrame 中筛选四类特殊交易记录。"""
    if df.empty:
        return df.copy()

    normalized = normalize_special_filter_config(
        load_special_filter_config() if config is None else config
    )
    mask = pd.Series(False, index=df.index)

    dates = normalized["特殊日期"]
    if normalized["启用特殊日期"] and dates:
        col_date = find_column(df.columns, ["日期"])
        if col_date:
            try:
                parsed = pd.to_datetime(df[col_date], errors="coerce")
                date_mask = parsed.dt.strftime("%m-%d").isin(dates)
                mask = mask | date_mask
                logger.debug("特殊日期规则命中: %s 条", int(date_mask.sum()))
            except Exception as exc:
                logger.warning("日期解析失败，跳过特殊日期规则: %s", exc)
        else:
            logger.warning("未找到「日期」列，跳过特殊日期规则")

    amount_patterns = normalized["金额模式"]
    if normalized["启用特殊金额"] and amount_patterns:
        col_amount = find_column(df.columns, ["交易", "金额", "元"])
        if col_amount:
            numeric = pd.to_numeric(df[col_amount], errors="coerce")
            amount_text = numeric.map(
                lambda value: f"{value:.2f}" if pd.notna(value) else ""
            )
            amount_mask = _literal_contains(amount_text, amount_patterns)
            mask = mask | amount_mask
            logger.debug("特殊金额规则命中: %s 条", int(amount_mask.sum()))
        else:
            logger.warning("未找到「交易金额(元)」列，跳过特殊金额规则")

    note_keywords = normalized["备注关键词"]
    if normalized["启用特殊备注"] and note_keywords:
        col_note2 = find_column(df.columns, ["备注2"])
        if col_note2:
            note_mask = _literal_contains(df[col_note2], note_keywords)
            mask = mask | note_mask
            logger.debug("特殊备注规则命中: %s 条", int(note_mask.sum()))
        else:
            logger.warning("未找到「备注2」列，跳过特殊备注规则")

    opponent_keywords = normalized["对手侧账户名称关键词"]
    if normalized["启用特殊对手方"] and opponent_keywords:
        col_opponent = find_column(df.columns, ["对手", "账户", "名称"])
        if col_opponent:
            opponent_mask = _literal_contains(df[col_opponent], opponent_keywords)
            mask = mask | opponent_mask
            logger.debug("特殊对手方规则命中: %s 条", int(opponent_mask.sum()))
        else:
            logger.warning("未找到「对手侧账户名称」列，跳过特殊对手方规则")

    result = df[mask].copy()
    logger.info(
        "特殊交易筛选: %s/%s 条 (%.1f%%)",
        len(result),
        len(df),
        len(result) / len(df) * 100,
    )
    return result