"""
配置读写服务 — 管理用户可写配置的验证和持久化

职责：
  - 读取停车缴费、时段分类、特殊交易和疑似麻友配置
  - 验证并保存用户修改的配置到持久化目录
  - 不依赖 pywebview 或线程

使用方式（由 bridge.py Api wrapper 转调）：
    from service.config_service import get_parking_config, save_parking_config
    from service.config_service import get_time_period_config, save_time_period_config
    from service.config_service import get_special_filter_config, save_special_filter_config
    from service.config_service import get_mahjong_config, save_mahjong_config
"""

import json
import os
import re
import logging

logger = logging.getLogger("TenpayMerge")


def _is_valid_time(value: str) -> bool:
    """校验 HH:MM 或 HH:MM:SS 时间字符串。"""
    from utils.time_utils import time_to_minutes
    return time_to_minutes(str(value)) >= 0


def _save_config_file(filename: str, config: dict, label: str) -> str:
    """保存配置到用户可写配置目录。"""
    try:
        from utils.paths import get_user_config_dir
        config_dir = get_user_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, filename)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"{label}已保存: {config_path}")
        return "ok"
    except Exception as e:
        return f"保存失败: {e}"


def get_parking_config() -> dict:
    """获取停车缴费识别配置（从用户配置或内置默认）。"""
    from core.parking import load_parking_config
    try:
        return load_parking_config()
    except Exception as e:
        return {"error": str(e)}


def save_parking_config(config: dict) -> str:
    """
    验证并保存停车缴费识别配置。

    Args:
        config: 配置字典

    Returns:
        "ok" 或错误信息字符串
    """
    required_fields = ["备注2关键词", "排除关键词", "对手侧账户名称关键词", "车牌省份简称"]
    for field in required_fields:
        if field not in config:
            return f"缺少必填字段: {field}"
        if not isinstance(config[field], list):
            return f"字段 {field} 必须是数组"

    return _save_config_file("parking_config.json", config, "停车配置")


def get_time_period_config() -> dict:
    """获取时段分类配置（从用户配置或内置默认）。"""
    from core.processor import load_time_period_config
    try:
        return load_time_period_config()
    except Exception as e:
        return {"error": str(e)}


def save_time_period_config(config: dict) -> str:
    """
    验证并保存时段分类配置。

    Args:
        config: 配置字典，必须包含 "时段" 列表

    Returns:
        "ok" 或错误信息字符串
    """
    if "时段" not in config or not isinstance(config["时段"], list):
        return "缺少必填字段: 时段"
    for period in config["时段"]:
        if not all(k in period for k in ("name", "start", "end")):
            return "每个时段必须包含 name, start, end"

    return _save_config_file("time_period_config.json", config, "时段配置")


def get_special_filter_config() -> dict:
    """获取特殊交易筛选配置（已转换为当前配置结构）。"""
    from core.special_filter import load_special_filter_config
    try:
        return load_special_filter_config()
    except Exception as e:
        return {"error": str(e)}


def _normalize_unique_strings(value: list) -> list[str]:
    """清理字符串列表并按输入顺序去重。"""
    result = []
    seen = set()
    for item in value:
        normalized = item.strip()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def save_special_filter_config(config: dict) -> str:
    """验证、规范化并保存特殊交易筛选配置。"""
    if not isinstance(config, dict):
        return "配置必须是对象"

    rule_fields = [
        ("启用特殊日期", "特殊日期"),
        ("启用特殊金额", "金额模式"),
        ("启用特殊备注", "备注关键词"),
        ("启用特殊对手方", "对手侧账户名称关键词"),
    ]
    normalized = {}
    for enabled_field, list_field in rule_fields:
        if enabled_field not in config or not isinstance(config[enabled_field], bool):
            return f"字段 {enabled_field} 必须是布尔值"
        if list_field not in config or not isinstance(config[list_field], list):
            return f"字段 {list_field} 必须是数组"
        if any(not isinstance(item, str) for item in config[list_field]):
            return f"字段 {list_field} 的每一项必须是字符串"

        values = _normalize_unique_strings(config[list_field])
        if config[enabled_field] and not values:
            return f"启用 {list_field} 时至少需要一个有效条目"
        normalized[enabled_field] = config[enabled_field]
        normalized[list_field] = values

    from core.special_filter import normalize_special_date

    dates = []
    for value in normalized["特殊日期"]:
        date_value = normalize_special_date(value)
        if date_value is None:
            return f"特殊日期格式无效: {value}，应为 M-D 或 MM-DD"
        if date_value not in dates:
            dates.append(date_value)
    normalized["特殊日期"] = dates

    for pattern in normalized["金额模式"]:
        if not re.fullmatch(r"\d+(?:\.\d{1,2})?", pattern):
            return f"金额模式格式无效: {pattern}，仅支持数字和最多两位小数"

    return _save_config_file(
        "special_filter_config.json", normalized, "特殊交易配置"
    )


def get_mahjong_config() -> dict:
    """获取疑似麻友识别配置（从用户配置或内置默认）。"""
    from core.mahjong import load_mahjong_config
    try:
        return load_mahjong_config()
    except Exception as e:
        return {"error": str(e)}


def save_mahjong_config(config: dict) -> str:
    """
    验证并保存疑似麻友识别配置。

    Args:
        config: 配置字典

    Returns:
        "ok" 或错误信息字符串
    """
    list_fields = ["商户排除关键词", "备注1匹配", "交易用途类型匹配"]
    for field in list_fields:
        if field not in config:
            return f"缺少必填字段: {field}"
        if not isinstance(config[field], list):
            return f"字段 {field} 必须是数组"

    int_fields = ["单晚最少对手方数", "单晚最多对手方数", "圈子最少对手方数", "最少出现天数"]
    for field in int_fields:
        try:
            if int(config.get(field, 0)) < 1:
                return f"字段 {field} 必须是不小于 1 的整数"
        except (TypeError, ValueError):
            return f"字段 {field} 必须是不小于 1 的整数"

    if int(config["单晚最多对手方数"]) < int(config["单晚最少对手方数"]):
        return "单晚最多对手方数不能小于单晚最少对手方数"

    if not _is_valid_time(config.get("分析开始时间", "")):
        return "分析开始时间格式无效，应为 HH:MM"
    if not _is_valid_time(config.get("分析结束时间", "")):
        return "分析结束时间格式无效，应为 HH:MM"
    if str(config.get("分析开始时间")).strip() == str(config.get("分析结束时间")).strip():
        return "分析开始时间和结束时间不能相同"

    normalized = dict(config)
    for field in int_fields:
        normalized[field] = int(normalized[field])
    normalized["分析开始时间"] = str(normalized["分析开始时间"]).strip().replace("：", ":")
    normalized["分析结束时间"] = str(normalized["分析结束时间"]).strip().replace("：", ":")

    return _save_config_file("mahjong_config.json", normalized, "疑似麻友配置")
