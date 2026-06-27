"""
去重模块测试 — scripts/core/merger.py
"""

import pandas as pd
import pytest
from core.merger import deduplicate


class TestDeduplicate:
    """deduplicate() 8列联合主键去重。"""

    def test_duplicate_rows_dropped(self):
        """完全相同的两行 → 仅保留1条。"""
        df = pd.DataFrame({
            "用户ID": ["U001", "U001"],
            "交易单号": ["T001", "T001"],
            "大单号": ["B001", "B001"],
            "日期": ["2026/4/2", "2026/4/2"],
            "时间": ["14:30", "14:30"],
            "借贷类型": ["出", "出"],
            "交易金额(元)": [100.0, 100.0],
            "对手方ID": ["P001", "P001"],
            "备注1": ["", ""],
        })
        result = deduplicate(df)
        assert len(result) == 1
        assert result.iloc[0]["用户ID"] == "U001"

    def test_no_duplicates_unchanged(self):
        """完全不同的行 → 不变。"""
        df = pd.DataFrame({
            "用户ID": ["U001", "U002"],
            "交易单号": ["T001", "T002"],
            "大单号": ["B001", "B002"],
            "日期": ["2026/4/2", "2026/4/3"],
            "时间": ["14:30", "15:00"],
            "借贷类型": ["出", "入"],
            "交易金额(元)": [100.0, 200.0],
            "对手方ID": ["P001", "P002"],
        })
        result = deduplicate(df)
        assert len(result) == 2

    def test_group_red_packet_not_removed(self):
        """
        群红包场景：7列完全相同，仅对手方ID不同。
        验证这些记录全部保留（不误删）。
        """
        df = pd.DataFrame({
            "用户ID": ["U001", "U001", "U001"],
            "交易单号": ["T001", "T001", "T001"],
            "大单号": ["B001", "B001", "B001"],
            "日期": ["2026/4/2", "2026/4/2", "2026/4/2"],
            "时间": ["10:00", "10:00", "10:00"],
            "借贷类型": ["出", "出", "出"],
            "交易金额(元)": [100.0, 100.0, 100.0],
            "对手方ID": ["P001", "P002", "P003"],
            "对手方接收金额(元)": [20.0, 30.0, 50.0],
        })
        result = deduplicate(df)
        # 3 条都应该保留（对手方ID 不同）
        assert len(result) == 3

    def test_partial_missing_columns(self):
        """部分去重列缺失 → 降级到可用列去重，不应崩溃。"""
        df = pd.DataFrame({
            "用户ID": ["U001", "U001"],
            "交易单号": ["T001", "T001"],
            "日期": ["2026/4/2", "2026/4/2"],
            "时间": ["14:30", "14:30"],
            "借贷类型": ["出", "出"],
            "交易金额(元)": [100.0, 100.0],
            "对手方ID": ["P001", "P001"],
            # 没有"大单号"列
        })
        result = deduplicate(df)
        assert len(result) == 1

    def test_empty_dataframe(self):
        """空 DataFrame → 返回空。"""
        df = pd.DataFrame()
        result = deduplicate(df)
        assert len(result) == 0

    def test_single_row(self):
        """单行 DataFrame → 不变。"""
        df = pd.DataFrame({
            "用户ID": ["U001"],
            "交易单号": ["T001"],
            "大单号": ["B001"],
            "日期": ["2026/4/2"],
            "时间": ["14:30"],
            "借贷类型": ["出"],
            "交易金额(元)": [100.0],
            "对手方ID": ["P001"],
        })
        result = deduplicate(df)
        assert len(result) == 1

    def test_no_column_overlap_fallback(self):
        """
        无任何去重列可用 → fallback 到全列去重。
        """
        df = pd.DataFrame({
            "col_a": [1, 1],
            "col_b": ["x", "x"],
        })
        result = deduplicate(df)
        assert len(result) == 1
