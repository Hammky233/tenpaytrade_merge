"""
配置读写服务 — 管理用户可写配置的验证和持久化

职责：
  - 读取停车缴费配置、时段分类配置
  - 验证并保存用户修改的配置到持久化目录
  - 不依赖 pywebview 或线程

使用方式（由 bridge.py Api wrapper 转调）：
    from service.config_service import get_parking_config, save_parking_config
    from service.config_service import get_time_period_config, save_time_period_config
"""

import json
import os
import logging

logger = logging.getLogger("TenpayMerge")


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

    try:
        from utils.paths import get_user_config_dir
        config_dir = get_user_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "parking_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"停车配置已保存: {config_path}")
        return "ok"
    except Exception as e:
        return f"保存失败: {e}"


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

    try:
        from utils.paths import get_user_config_dir
        config_dir = get_user_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "time_period_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"时段配置已保存: {config_path}")
        return "ok"
    except Exception as e:
        return f"保存失败: {e}"
