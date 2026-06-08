"""
文件读取模块（仅处理 TenpayTrades.txt）

- 自动检测编码（UTF-8 优先，fallback 到 GBK）
- tab 分隔解析
- 跳过空文件（≤ 1KB）
- 跳过重复表头行
- 处理列溢出（多余列合并到最后一列）
"""

import os
import logging
import pandas as pd

logger = logging.getLogger("TenpayMerge")

# 最小有效文件大小（字节），小于此值视为空文件（仅含表头）
MIN_FILE_SIZE = 1024  # 1KB


def read_tenpay_trades(filepath: str) -> pd.DataFrame | None:
    """
    读取单个 TenpayTrades.txt 文件

    Args:
        filepath: txt 文件路径

    Returns:
        DataFrame 或 None（读取失败/空文件时）
    """
    # 预检查：文件大小
    try:
        size = os.path.getsize(filepath)
        if size <= MIN_FILE_SIZE:
            logger.info(f"跳过空文件（{size}B）: ...{os.path.sep}{os.path.basename(os.path.dirname(filepath))}{os.path.sep}{os.path.basename(filepath)}")
            return None
    except OSError:
        pass

    # 尝试多种编码读取
    content = None
    for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-16']:
        try:
            with open(filepath, 'r', encoding=encoding, errors='replace') as f:
                content = f.readlines()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if content is None:
        logger.error(f"无法识别编码: {filepath}")
        return None

    if not content:
        logger.warning(f"文件为空: {filepath}")
        return None

    # 解析表头（第一行）
    header_line = content[0].strip()
    if not header_line:
        logger.warning(f"表头行为空: {filepath}")
        return None

    header = [col.strip() for col in header_line.split('\t')]
    expected_cols = len(header)

    # 解析数据行
    data_rows = []
    for i, line in enumerate(content[1:], 1):
        line = line.strip()
        if not line:
            continue

        parts = line.split('\t')

        # 跳过重复的表头行
        if len(parts) == len(header) and parts == header:
            continue

        # 列数溢出：合并多余列到最后一列
        if len(parts) > expected_cols:
            extra = '\t'.join(parts[expected_cols - 1:])
            parts = parts[:expected_cols - 1] + [extra]
        # 列数不足：补空
        elif len(parts) < expected_cols:
            parts.extend([''] * (expected_cols - len(parts)))

        data_rows.append(parts)

    if not data_rows:
        logger.warning(f"无有效数据行: {filepath}")
        return None

    # 构建 DataFrame（所有列以字符串读入，避免银行卡号科学计数法）
    df = pd.DataFrame(data_rows, columns=header, dtype=str)
    logger.debug(f"读取: {len(df)} 行, {len(df.columns)} 列")

    return df
