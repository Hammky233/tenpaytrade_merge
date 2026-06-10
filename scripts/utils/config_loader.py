"""
统一 JSON 配置加载器

所有业务配置文件位于 scripts/config/，通过此模块统一加载。
替换 ad-hoc 的 config 加载逻辑（processor、parking、special_filter 各自实现不同模式）。
"""

import os
import json
import logging

logger = logging.getLogger("TenpayMerge")


def load_json_config(name: str, defaults: dict) -> dict:
    """
    从 scripts/config/<name>.json 加载 JSON 配置。

    支持开发环境和 PyInstaller 打包环境（通过 utils.paths.get_config_dir()）。

    Args:
        name: 配置文件名（不含 .json 后缀），如 "parking_config"
        defaults: 文件不存在或解析失败时返回的默认配置

    Returns:
        配置字典
    """
    from utils.paths import get_config_dir

    config_path = os.path.join(get_config_dir(), f"{name}.json")

    if not os.path.exists(config_path):
        logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
        return defaults

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        logger.debug(f"配置已加载: {config_path}")
        return config
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"配置文件解析失败 ({config_path}): {e}，使用默认配置")
        return defaults
