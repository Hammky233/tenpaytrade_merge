"""
时间拆分测试 — scripts/core/processor.py

测试 split_datetime() 函数行为。
"""

import pandas as pd
import pytest
from core.processor import split_datetime


class TestSplitDatetime:
    """split_datetime() — 交易时间→日期+时间拆分。"""

    def test_standard_split(self):
        """
        标准格式 "2026/4/2 14:30:00"
        → 日期列 "2026/4/2" 时间列 "14:30:00"
        """
        df = pd.DataFrame({
            "交易用途类型": ["转账"],
            "交易时间": ["2026/4/2 14:30:00"],
            "其他列": ["x"],
        })
        result = split_datetime(df)
        assert "日期" in result.columns
        assert "时间" in result.columns
        assert "交易时间" not in result.columns
        assert result.iloc[0]["日期"] == "2026/4/2"
        assert result.iloc[0]["时间"] == "14:30:00"

    def test_split_no_seconds(self):
        """不带秒的格式。"""
        df = pd.DataFrame({
            "交易用途类型": ["消费"],
            "交易时间": ["2026-04-02 09:05"],
        })
        result = split_datetime(df)
        assert result.iloc[0]["日期"] == "2026/4/2"
        assert result.iloc[0]["时间"] == "09:05"

    def test_column_position_after_purpose(self):
        """日期/时间列应插入在"交易用途类型"列之后。"""
        df = pd.DataFrame({
            "借贷类型": ["出"],
            "交易用途类型": ["转账"],
            "交易时间": ["2026/4/2 14:30:00"],
            "交易金额": ["100"],
        })
        result = split_datetime(df)
        cols = list(result.columns)
        assert "日期" in cols
        assert "时间" in cols
        # 日期/时间应在"交易用途类型"之后
        type_pos = cols.index("交易用途类型")
        date_pos = cols.index("日期")
        time_pos = cols.index("时间")
        assert date_pos == type_pos + 1
        assert time_pos == type_pos + 2

    def test_no_time_column(self):
        """无"交易时间"列 → 跳过，不报错。"""
        df = pd.DataFrame({
            "交易用途类型": ["转账"],
            "金额": ["100"],
        })
        result = split_datetime(df)
        assert "日期" not in result.columns
        assert "时间" not in result.columns
        assert len(result) == 1

    def test_empty_dataframe(self):
        """空 DataFrame → 返回空。"""
        df = pd.DataFrame()
        result = split_datetime(df)
        assert len(result) == 0

    def test_null_time_value(self):
        """交易时间为空值 → 日期时间留空。"""
        df = pd.DataFrame({
            "交易用途类型": ["转账"],
            "交易时间": [None],
        })
        result = split_datetime(df)
        assert "日期" in result.columns
        assert "时间" in result.columns
