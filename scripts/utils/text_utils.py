"""
文本解析工具 — Tab 分隔行标准化

处理财付通 txt 导出中列溢出/不足的通用逻辑。
"""


def normalize_row_parts(parts: list[str], expected_cols: int) -> list[str]:
    """
    标准化 Tab 分隔的列列表，使其长度对齐表头列数。

    规则：
    - 列数溢出：多余列合并到最后一列（用 Tab 拼接）
    - 列数不足：用空字符串补齐

    Args:
        parts: 原始列字符串列表
        expected_cols: 表头列数

    Returns:
        长度等于 expected_cols 的列列表
    """
    if len(parts) > expected_cols:
        extra = '\t'.join(parts[expected_cols - 1:])
        parts = parts[:expected_cols - 1] + [extra]
    elif len(parts) < expected_cols:
        parts.extend([''] * (expected_cols - len(parts)))
    return parts
