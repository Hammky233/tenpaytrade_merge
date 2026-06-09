"""
停车缴费识别模块

功能：
  detect_parking_records(df, config) → 从去重后的 DataFrame 筛选停车缴费记录
  extract_license_plate(text, provinces) → 从备注文本中提取车牌号
  add_license_plate_column(df, provinces) → 添加"车牌"列
  load_parking_config(config_path) → 加载配置文件
"""

import os
import re
import json
import logging
import pandas as pd
from .processor import find_column

logger = logging.getLogger("TenpayMerge")

# 默认配置路径（相对于项目根目录）
_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "parking_config.json"
)


def load_parking_config(config_path: str | None = None) -> dict:
    """
    加载停车识别配置文件。

    Args:
        config_path: 配置文件路径，默认 scripts/config/parking_config.json

    Returns:
        配置字典
    """
    path = config_path or _DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        logger.warning(f"停车配置不存在: {path}，使用默认配置")
        return {
            "备注2关键词": ["停车缴费", "停车费", "停车", "停车场", "临停缴费"],
            "排除关键词": [],
            "对手侧账户名称关键词": ["停车"],
            "车牌省份简称": [
                "京", "津", "沪", "渝", "冀", "豫", "云", "辽", "黑",
                "湘", "皖", "鲁", "新", "苏", "浙", "赣", "鄂", "桂", "甘",
                "晋", "蒙", "陕", "吉", "闽", "贵", "粤", "川", "青", "藏", "琼", "宁",
            ],
        }

    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    logger.debug(f"停车配置已加载: {path}")
    return config


# ============================================================================
# 车牌提取
# ============================================================================

def _clean_special_chars(text: str) -> str:
    """清理特殊 Unicode 控制字符（与 processor.py 保持一致）"""
    special_chars = ['‌', '‎', '‪', '‬', '‍', '​', '‏']
    for char in special_chars:
        text = text.replace(char, '')
    return text


def extract_license_plate(text: str, provinces: list[str]) -> str | None:
    """
    从备注文本中提取车牌号。

    匹配规则：
    - 省份简称 + 字母 + 5~6 位字母数字（允许字符间穿插 '-'）
    - 优先匹配 5 位（标准蓝牌），6 位仅在上下文合理时取

    Args:
        text: 备注文本（如备注2内容）
        provinces: 车牌省份简称列表

    Returns:
        干净车牌号（无 '-'）或 None
    """
    if pd.isna(text) or not isinstance(text, str) or not text.strip():
        return None

    # 清理特殊 Unicode 字符
    text = _clean_special_chars(text)
    if not text:
        return None

    # 构建省份简称字符类
    province_class = ''.join(provinces)

    # 构建正则：省份 + opt_hyphen + 字母 + opt_hyphen + 5 位字母数字（各允许 opt_hyphen）
    # 再可选第 6 位（opt_hyphen + 字母数字），但仅当它不是以 '-' 开头的纯数字段时
    #
    # 匹配组: (省份)(城市字母)(位1)(位2)(位3)(位4)(位5)[(位6)]
    pattern = (
        f'([{province_class}])'       # 组1: 省份简称
        r'[\-]?'                        # 可选 '-'
        r'([A-Z])'                      # 组2: 城市字母
        r'[\-]?'                        # 可选 '-'
        r'([A-Z0-9])'                   # 组3: 位1
        r'[\-]?'                        # 可选 '-'
        r'([A-Z0-9])'                   # 组4: 位2
        r'[\-]?'                        # 可选 '-'
        r'([A-Z0-9])'                   # 组5: 位3
        r'[\-]?'                        # 可选 '-'
        r'([A-Z0-9])'                   # 组6: 位4
        r'[\-]?'                        # 可选 '-'
        r'([A-Z0-9])'                   # 组7: 位5 (标准 5 位截止于此)
        r'('                            # 组8（可选）: 第 6 位
            r'[\-]?'                    #   可选 '-'
            r'[A-Z0-9]'                 #   位6
        r')?'
    )

    matches = list(re.finditer(pattern, text))

    if not matches:
        return None

    # 取第一个匹配
    best_plate = None

    for m in matches:
        groups = m.groups()
        province = groups[0]
        city = groups[1]
        # 5 位主体
        chars_5 = ''.join(g for g in groups[2:7] if g)
        plate_5 = f"{province}{city}{chars_5}"

        # 检查是否存在第 6 位
        has_6th = groups[7] is not None

        if has_6th:
            # 第 6 位存在，需要判断是否真的属于车牌
            # 策略：检查原文中第 6 位之前的上下文
            # 如果匹配位置后面紧跟着以 '-' 开头的数字串，则第 6 位可能属于参考号
            end_5 = m.start() + len(province)  # 起点
            # 找到第 5 位结束位置
            match_text = m.group(0)
            # group(7) 的内容
            sixth_part = groups[7]
            if sixth_part:
                # 去掉 leading hyphen
                sixth_char = sixth_part.replace('-', '')
                plate_6 = plate_5 + sixth_char

                # 判断 6 位是否合理：
                # 如果原文字中，第 5 位和第 6 位之间有 '-' 分隔，
                # 且第 6 位后面紧跟数字，则认为是参考号的一部分，取 5 位
                match_end = m.end()
                rest = text[match_end:] if match_end < len(text) else ""

                # 第 6 位以 '-' 开头（组中带 hyphen），且后面紧跟多位数字 → 参考号
                if sixth_part.startswith('-'):
                    # 看看后面是不是一连串数字（参考号特征）
                    if re.match(r'^\d{2,}', rest):
                        # 很可能是参考号，取 5 位
                        best_plate = plate_5
                        break
                    # 如果后面是 '-' 继续或直接是数字串，也取 5 位
                    if re.match(r'^[\-]?\d+', rest):
                        best_plate = plate_5
                        break

                # 检查第 6 位是否是 P + 数字（参考号常见模式：P181106412）
                if sixth_char.upper() == 'P' and re.match(r'^\d+', rest):
                    best_plate = plate_5
                    break

                # 否则取 6 位
                best_plate = plate_6
                break
        else:
            # 只有 5 位
            best_plate = plate_5
            break

    if best_plate is None and matches:
        # fallback: 取第一个匹配的 5 位
        m = matches[0]
        groups = m.groups()
        best_plate = f"{groups[0]}{groups[1]}{''.join(g for g in groups[2:7] if g)}"

    return best_plate


def add_license_plate_column(df: pd.DataFrame, provinces: list[str]) -> pd.DataFrame:
    """
    在 DataFrame 最右侧添加"车牌"列。
    对每行的「备注2」列提取车牌号，无法识别的填"无"。

    Args:
        df: 输入 DataFrame
        provinces: 车牌省份简称列表

    Returns:
        添加了"车牌"列的 DataFrame
    """
    df = df.copy()

    # 用 find_column 自适应找到备注2列
    col_note2 = find_column(df.columns, ['备注2'])
    if not col_note2:
        # fallback: 尝试找"备注"
        col_note2 = find_column(df.columns, ['备注'])

    if col_note2:
        df['车牌'] = df[col_note2].apply(lambda x: extract_license_plate(x, provinces) or "无")
    else:
        logger.warning("未找到「备注2」列，车牌提取将全部标记为'无'")
        df['车牌'] = "无"

    logger.info(f"车牌提取完成: {(df['车牌'] != '无').sum()}/{len(df)} 条识别到车牌")
    return df


# ============================================================================
# 停车记录识别
# ============================================================================

def _contains_any(text: str, keywords: list[str]) -> bool:
    """检查文本是否包含任一关键词"""
    if pd.isna(text) or not isinstance(text, str):
        return False
    for kw in keywords:
        if kw in text:
            return True
    return False


def _contains_all(text: str, keywords: list[str]) -> bool:
    """检查文本是否包含所有关键词"""
    if pd.isna(text) or not isinstance(text, str):
        return False
    return all(kw in text for kw in keywords)


def detect_parking_records(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    从去重后的 DataFrame 中筛选停车缴费记录。

    筛选逻辑：
    1. 优先匹配「备注2」列：包含任一 include 关键词，且不包含任一 exclude 关键词
    2. 其次匹配「对手侧账户名称」列：包含对手侧关键词

    Args:
        df: 去重后的完整 DataFrame
        config: 停车识别配置字典

    Returns:
        停车缴费记录 DataFrame（含全部原始列）
    """
    if df.empty:
        return df.copy()

    include_keywords = config.get("备注2关键词", ["停车"])
    exclude_keywords = config.get("排除关键词", [])
    opponent_keywords = config.get("对手侧账户名称关键词", ["停车"])

    # 自适应识别列名
    col_note2 = find_column(df.columns, ['备注2'])
    col_opponent = find_column(df.columns, ['对手', '账户', '名称'])

    mask_parking = pd.Series(False, index=df.index)

    # 规则1：备注2 匹配
    if col_note2:
        mask_include = pd.Series(False, index=df.index)
        for kw in include_keywords:
            mask_include = mask_include | df[col_note2].astype(str).str.contains(kw, na=False)

        mask_exclude = pd.Series(False, index=df.index)
        for kw in exclude_keywords:
            mask_exclude = mask_exclude | df[col_note2].astype(str).str.contains(kw, na=False)

        mask_parking = mask_parking | (mask_include & ~mask_exclude)
    else:
        logger.warning("未找到「备注2」列，跳过备注2匹配")

    # 规则2：对手侧账户名称 匹配
    if col_opponent:
        mask_opponent = pd.Series(False, index=df.index)
        for kw in opponent_keywords:
            mask_opponent = mask_opponent | df[col_opponent].astype(str).str.contains(kw, na=False)
        mask_parking = mask_parking | mask_opponent
    else:
        logger.warning("未找到「对手侧账户名称」列，跳过对手方匹配")

    result = df[mask_parking].copy()

    logger.info(
        f"停车缴费识别: {len(result)}/{len(df)} 条 "
        f"({len(result)/len(df)*100:.1f}%)"
    )

    return result
