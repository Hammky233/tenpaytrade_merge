"""
编码检测工具 — 自动检测文本文件编码并读取

策略：依次尝试常见中文编码（utf-8 / gbk / gb2312 / utf-16），
使用 errors='replace' 模式确保损坏字节不会导致读取失败。
"""

import logging

logger = logging.getLogger("TenpayMerge")

# 按优先级排列的编码尝试列表
_ENCODINGS = ['utf-8', 'gbk', 'gb2312', 'utf-16']


def detect_and_read_lines(filepath: str) -> list[str] | None:
    """
    自动检测编码并读取文件所有行。

    依次用 utf-8 → gbk → gb2312 → utf-16 尝试读取（errors='replace'），
    首次成功即返回。所有编码均无法打开时返回 None。

    Args:
        filepath: 文件路径

    Returns:
        文件行列表（含换行符）或 None（无法读取时）
    """
    for encoding in _ENCODINGS:
        try:
            with open(filepath, 'r', encoding=encoding, errors='replace') as f:
                return f.readlines()
        except (UnicodeDecodeError, UnicodeError, OSError):
            continue
    return None
