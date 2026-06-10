"""
自适应列名识别工具

通过关键词交集匹配列名，避免硬编码列位置。
腾讯返回的字段顺序和名称可能变化，所有列名通过关键词组合定位。
"""


def find_column(columns, keywords):
    """
    精准匹配列名：必须同时包含所有关键词。
    返回第一个匹配到的列名（str）或 None。

    Args:
        columns: 列名列表（pd.Index 或 list）
        keywords: 关键词列表，所有关键词必须同时出现在列名中

    Returns:
        匹配到的列名（str）或 None
    """
    for col in columns:
        col_str = str(col)
        if all(k in col_str for k in keywords):
            return col_str
    return None


def find_columns_containing(columns, keywords):
    """
    查找所有包含指定关键词组合的列。
    用于查找多个金额列等场景。

    Args:
        columns: 列名列表
        keywords: 关键词列表，所有关键词必须同时出现在列名中

    Returns:
        匹配到的列名列表（可能为空）
    """
    result = []
    for col in columns:
        col_str = str(col)
        if all(k in col_str for k in keywords):
            result.append(col_str)
    return result
