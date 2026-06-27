"""
时间工具 — 时间字符串解析

供 processor.py（时段分类）和 mahjong.py（麻友识别）共享。
"""

import pandas as pd


def time_to_minutes(time_str: str) -> int:
    """
    将时间字符串 (HH:MM 或 HH:MM:SS) 转为分钟数。

    支持全角冒号（中文输入法）→ 半角冒号归一化。
    含边界校验：小时 0-23，分钟 0-59，非法输入返回 -1。

    Args:
        time_str: 时间字符串

    Returns:
        分钟数 (0~1439)，解析失败返回 -1
    """
    if pd.isna(time_str) or not isinstance(time_str, str):
        return -1
    try:
        # 归一化冒号：全角冒号（中文输入法）→ 半角冒号
        cleaned = str(time_str).strip().replace('：', ':')
        parts = cleaned.split(':')
        if len(parts) < 2:
            return -1
        hours = int(parts[0])
        minutes = int(parts[1])
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            return -1
        return hours * 60 + minutes
    except (ValueError, IndexError):
        return -1
