"""
文本清洗工具 — 统一处理腾讯 CSV 导出中的特殊 Unicode 控制字符
"""

import re


# 权威特殊字符列表（合并所有模块的字符集）
SPECIAL_CHARS = [
    '﻿',   # BOM (ZERO WIDTH NO-BREAK SPACE)  — "﻿"
    '‎',   # LEFT-TO-RIGHT MARK               — "‎"
    '‪',   # LEFT-TO-RIGHT EMBEDDING          — "‪"
    '‬',   # POP DIRECTIONAL FORMATTING       — "‬"
    '‌',   # ZERO WIDTH NON-JOINER            — "‌"
    '​',   # ZERO WIDTH SPACE                 — "​"
    '‍',   # ZERO WIDTH JOINER                 — "‍"
    '‏',   # RIGHT-TO-LEFT MARK                — "‏"
]

# 预编译正则（用于 pandas Series 向量化替换）
_SPECIAL_CHARS_REGEX = re.compile('|'.join(re.escape(c) for c in SPECIAL_CHARS))


def clean_special_chars(text: str) -> str:
    """移除字符串中所有已知的特殊 Unicode 控制字符"""
    for char in SPECIAL_CHARS:
        text = text.replace(char, '')
    return text


def clean_special_chars_str(text: str) -> str:
    """
    用正则移除字符串中的所有特殊字符。
    性能优于逐个字符替换，适合批量调用。
    """
    return _SPECIAL_CHARS_REGEX.sub('', text)


def clean_special_chars_series(series):
    """
    向量化版本：对整列 pandas Series 一次性移除所有特殊字符。
    用于 DataFrame 列级别的批量清理。

    Args:
        series: pandas Series

    Returns:
        清理后的 pandas Series
    """
    return series.str.replace(_SPECIAL_CHARS_REGEX, '', regex=True)
