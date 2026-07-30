"""
疑似麻友识别测试 — scripts/core/mahjong.py
"""

import pandas as pd

from core.mahjong import detect_mahjong_records


def _base_config(**overrides):
    config = {
        "商户排除关键词": ["公司", "超市"],
        "单晚最少对手方数": 2,
        "单晚最多对手方数": 10,
        "圈子最少对手方数": 2,
        "最少出现天数": 2,
        "分析开始时间": "20:00",
        "分析结束时间": "02:00",
        "备注1匹配": ["微信红包", "微信转账"],
        "交易用途类型匹配": ["转账"],
    }
    config.update(overrides)
    return config


def _row(date, time, opponent, amount, purpose="转账", note1="微信转账", opponent_id=None):
    return {
        "日期": date,
        "时间": time,
        "交易用途类型": purpose,
        "备注1": note1,
        "用户侧账号名称": "用户甲",
        "对手方ID": opponent_id or opponent,
        "对手侧账户名称": opponent,
        "交易金额(元)": amount,
    }


def test_detects_repeated_night_circle_and_keeps_high_amount():
    """多晚固定对手方共同出现应命中，金额数万元不应被排除。"""
    df = pd.DataFrame([
        _row("2026/4/1", "20:10:00", "张三", 1200),
        _row("2026/4/1", "20:20:00", "李四", 30000),
        _row("2026/4/2", "21:10:00", "张三", 1800),
        _row("2026/4/2", "21:20:00", "李四", 50000),
        _row("2026/4/2", "14:20:00", "王五", 1000),
        _row("2026/4/2", "21:30:00", "便利超市", 1000),
        _row("2026/4/2", "21:40:00", "赵六", 1000, purpose="消费"),
    ])

    detail_df, stats_df, circle_df = detect_mahjong_records(df, _base_config())

    assert set(stats_df["对手侧账户名称"]) == {"张三", "李四"}
    assert len(detail_df) == 4
    assert len(circle_df) == 1
    assert circle_df.iloc[0]["共同出现晚数"] == 2
    assert circle_df.iloc[0]["涉及总金额(元)"] == 83000
    assert stats_df.loc[stats_df["对手侧账户名称"] == "李四", "最高单笔金额(元)"].iloc[0] == 50000


def test_daytime_and_non_transfer_records_do_not_hit():
    """白天交易和非转账用途不应参与疑似麻友识别。"""
    df = pd.DataFrame([
        _row("2026/4/1", "14:10:00", "张三", 1000),
        _row("2026/4/1", "14:20:00", "李四", 1000),
        _row("2026/4/2", "21:10:00", "张三", 1000, purpose="消费"),
        _row("2026/4/2", "21:20:00", "李四", 1000, purpose="消费"),
    ])

    detail_df, stats_df, circle_df = detect_mahjong_records(df, _base_config())

    assert detail_df.empty
    assert stats_df.empty
    assert circle_df.empty


def test_merchant_keyword_exclusion_remains_effective():
    """商户关键词命中的对手方不应视为自然人固定圈子成员。"""
    df = pd.DataFrame([
        _row("2026/4/1", "20:10:00", "张三", 1000),
        _row("2026/4/1", "20:20:00", "某某公司", 1000),
        _row("2026/4/2", "21:10:00", "张三", 1000),
        _row("2026/4/2", "21:20:00", "某某公司", 1000),
    ])

    detail_df, stats_df, circle_df = detect_mahjong_records(df, _base_config())

    assert detail_df.empty
    assert stats_df.empty
    assert circle_df.empty


def test_custom_analysis_window_changes_result():
    """修改分析时段后，原默认时段外的固定圈子可以被识别。"""
    df = pd.DataFrame([
        _row("2026/4/1", "19:10:00", "张三", 1000),
        _row("2026/4/1", "19:20:00", "李四", 1000),
        _row("2026/4/2", "19:10:00", "张三", 1000),
        _row("2026/4/2", "19:20:00", "李四", 1000),
    ])

    default_detail, _, _ = detect_mahjong_records(df, _base_config())
    custom_detail, custom_stats, custom_circle = detect_mahjong_records(
        df,
        _base_config(分析开始时间="19:00", 分析结束时间="22:00"),
    )

    assert default_detail.empty
    assert len(custom_detail) == 4
    assert set(custom_stats["对手侧账户名称"]) == {"张三", "李四"}
    assert len(custom_circle) == 1
