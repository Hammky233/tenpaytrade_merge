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
    从 JSON 配置文件加载配置。

    读取策略（双层降级）：
      1. 优先从用户配置目录（get_user_config_dir()）加载
      2. 未找到则从内置默认配置目录（get_config_dir()）加载
      3. 均未找到则返回 defaults

    开发环境下用户配置目录 === 内置配置目录，行为完全向后兼容。

    Args:
        name: 配置文件名（不含 .json 后缀），如 "parking_config"
        defaults: 文件不存在或解析失败时返回的默认配置

    Returns:
        配置字典
    """
    from utils.paths import get_config_dir, get_user_config_dir

    # 搜索路径：用户配置优先 → 内置默认配置兜底
    search_paths = [get_user_config_dir(), get_config_dir()]
    errors = []

    for config_dir in search_paths:
        config_path = os.path.join(config_dir, f"{name}.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                logger.debug(f"配置已加载: {config_path}")
                return config
            except (json.JSONDecodeError, OSError) as e:
                errors.append(f"{config_path}: {e}")
                continue  # 尝试下一个路径
        else:
            errors.append(f"{config_path}: 不存在")

    # 所有路径均失败，使用默认值
    logger.warning(
        f"配置文件 {name}.json 加载失败（{'; '.join(errors)}），使用默认配置"
    )
    return defaults
