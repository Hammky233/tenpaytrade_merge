"""特殊交易筛选配置和四类规则测试。"""

import pandas as pd

from core.special_filter import (
    default_special_filter_config,
    detect_special_records,
    normalize_special_filter_config,
    normalize_special_date,
)


def _config(**overrides):
    config = {
        "启用特殊日期": False,
        "特殊日期": ["02-14"],
        "启用特殊金额": False,
        "金额模式": ["520"],
        "启用特殊备注": False,
        "备注关键词": ["快乐"],
        "启用特殊对手方": False,
        "对手侧账户名称关键词": ["足浴"],
    }
    config.update(overrides)
    return config


def _rows():
    return pd.DataFrame([
        {
            "日期": "2025/2/14",
            "交易金额(元)": 10,
            "备注2": "普通消费",
            "对手侧账户名称": "普通商户",
        },
        {
            "日期": "2026/3/1",
            "交易金额(元)": 520,
            "备注2": "普通消费",
            "对手侧账户名称": "普通商户",
        },
        {
            "日期": "2026/3/2",
            "交易金额(元)": 20,
            "备注2": "祝你快乐",
            "对手侧账户名称": "普通商户",
        },
        {
            "日期": "2026/3/3",
            "交易金额(元)": 30,
            "备注2": "普通消费",
            "对手侧账户名称": "阳光足浴中心",
        },
    ])


def test_new_default_rules_include_requested_dates_and_keywords():
    """内置默认值应包含新增日期和关注场所关键词。"""
    config = default_special_filter_config()
    expected = [
        "桑拿", "足浴", "休闲", "会所", "按摩", "养生",
        "足疗", "SPA", "spa", "温泉", "酒店",
    ]
    assert config["特殊日期"] == ["02-14", "05-20"]
    assert config["启用特殊对手方"] is True
    assert config["对手侧账户名称关键词"] == expected
    assert all(keyword in config["备注关键词"] for keyword in expected)


def test_explicit_new_opponent_settings_are_not_overwritten_by_defaults():
    """用户已保存的新结构关闭状态和空列表应保持不变。"""
    normalized = normalize_special_filter_config({
        "启用特殊对手方": False,
        "对手侧账户名称关键词": [],
    })
    assert normalized["启用特殊对手方"] is False
    assert normalized["对手侧账户名称关键词"] == []


def test_four_rules_hit_independently_and_use_or_relation():
    """四类规则应分别命中，全部启用时按 OR 合并。"""
    df = _rows()
    for enabled_field, expected_index in [
        ("启用特殊日期", 0),
        ("启用特殊金额", 1),
        ("启用特殊备注", 2),
        ("启用特殊对手方", 3),
    ]:
        result = detect_special_records(df, _config(**{enabled_field: True}))
        assert list(result.index) == [expected_index]

    all_enabled = _config(
        启用特殊日期=True,
        启用特殊金额=True,
        启用特殊备注=True,
        启用特殊对手方=True,
    )
    assert list(detect_special_records(df, all_enabled).index) == [0, 1, 2, 3]


def test_date_rule_repeats_across_years_and_supports_leap_day():
    """月日规则应跨年份生效，并允许 02-29。"""
    df = pd.DataFrame({
        "日期": ["2024/2/29", "2025/2/28", "2026/2/14", "2027/2/14"],
    })
    result = detect_special_records(
        df,
        _config(启用特殊日期=True, 特殊日期=["2-29", "02-14"]),
    )
    assert list(result.index) == [0, 2, 3]
    assert normalize_special_date("2-9") == "02-09"
    assert normalize_special_date("02-30") is None


def test_disabled_rules_keep_values_but_do_not_match():
    """关闭规则时应保留配置值但不产生命中。"""
    config = _config()
    normalized = normalize_special_filter_config(config)
    assert normalized["对手侧账户名称关键词"] == ["足浴"]
    assert detect_special_records(_rows(), config).empty


def test_text_patterns_are_literal_not_regular_expressions():
    """金额和备注配置中的正则字符必须按普通文本处理。"""
    df = pd.DataFrame({
        "交易金额(元)": [510, 15],
        "备注2": ["普通备注", "包含.字符"],
    })
    amount_result = detect_special_records(
        df, _config(启用特殊金额=True, 金额模式=["5.1"])
    )
    note_result = detect_special_records(
        df, _config(启用特殊备注=True, 备注关键词=["."])
    )
    assert amount_result.empty
    assert list(note_result.index) == [1]


def test_missing_opponent_column_only_skips_opponent_rule():
    """缺少对手字段时不应影响其他规则。"""
    df = pd.DataFrame({"日期": ["2026/2/14"], "备注2": [""]})
    result = detect_special_records(
        df,
        _config(启用特殊日期=True, 启用特殊对手方=True),
    )
    assert len(result) == 1


def test_legacy_config_receives_new_rule_defaults():
    """旧版 2 月 14 日开关及金额、备注列表应转换为新结构。"""
    migrated = normalize_special_filter_config({
        "启用2月14日": False,
        "金额模式": ["520"],
        "备注关键词": [],
    })
    assert migrated["启用特殊日期"] is False
    assert migrated["特殊日期"] == ["02-14", "05-20"]
    assert migrated["启用特殊金额"] is True
    assert migrated["启用特殊备注"] is False
    assert migrated["启用特殊对手方"] is True
    assert "足浴" in migrated["对手侧账户名称关键词"]