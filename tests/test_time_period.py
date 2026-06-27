"""
时段分类测试 — scripts/core/processor.py

测试 classify_time_period() 函数行为。
"""

import pandas as pd
import pytest
from core.processor import classify_time_period


class TestClassifyTimePeriod:
    """classify_time_period() — 时间→时段分类。"""

    def test_morning_boundary(self, time_period_config):
        """06:00 → 早上（下边界）。"""
        df = pd.DataFrame({"时间": ["06:00"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "早上"

    def test_early_morning_before_six(self, time_period_config):
        """05:59 → 凌晨（上边界）。"""
        df = pd.DataFrame({"时间": ["05:59"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "凌晨"

    def test_midnight(self, time_period_config):
        """00:00 → 凌晨（起始边界）。"""
        df = pd.DataFrame({"时间": ["00:00"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "凌晨"

    def test_morning(self, time_period_config):
        """08:30 → 早上。"""
        df = pd.DataFrame({"时间": ["08:30"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "早上"

    def test_afternoon(self, time_period_config):
        """14:30 → 下午。"""
        df = pd.DataFrame({"时间": ["14:30"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "下午"

    def test_evening(self, time_period_config):
        """19:30 → 晚上。"""
        df = pd.DataFrame({"时间": ["19:30"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "晚上"

    def test_evening_2359(self, time_period_config):
        """23:59 → 晚上。"""
        df = pd.DataFrame({"时间": ["23:59"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "晚上"

    def test_noon_boundary(self, time_period_config):
        """12:00 → 下午（start ≤ minutes < end, 12:00 属于下午的下边界）。"""
        df = pd.DataFrame({"时间": ["12:00"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "下午"

    def test_evening_boundary(self, time_period_config):
        """19:00 → 晚上（晚上的下边界）。"""
        df = pd.DataFrame({"时间": ["19:00"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "晚上"

    def test_invalid_24_00(self, time_period_config):
        """24:00 → "未知"（小时 24 超出 time_to_minutes 校验范围 0-23）。"""
        df = pd.DataFrame({"时间": ["24:00"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "未知"

    def test_fullwidth_colon(self, time_period_config):
        """全角冒号 `14：30` → 归一化为半角后分类正确。"""
        df = pd.DataFrame({"时间": ["14：30"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "下午"

    def test_invalid_time(self, time_period_config):
        """非法时间字符串 → "未知"。"""
        df = pd.DataFrame({"时间": ["abc"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "未知"

    def test_empty_time(self, time_period_config):
        """空字符串 → "未知"。"""
        df = pd.DataFrame({"时间": [""]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "未知"

    def test_idempotent(self, time_period_config):
        """已有"时段"列 → 跳过，不覆盖。"""
        df = pd.DataFrame({"时间": ["08:30"], "时段": ["自定义"]})
        result = classify_time_period(df, time_period_config)
        assert result.iloc[0]["时段"] == "自定义"

    def test_no_time_column(self, time_period_config):
        """无"时间"列 → 跳过，不报错。"""
        df = pd.DataFrame({"金额": [100]})
        result = classify_time_period(df, time_period_config)
        assert "时段" not in result.columns
