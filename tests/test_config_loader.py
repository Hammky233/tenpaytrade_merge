"""
测试 scripts/utils/config_loader.py 双层配置加载策略。

覆盖以下场景：
- 用户目录有配置 → 加载用户配置
- 仅内置目录有配置 → 加载内置配置
- 均无 → 返回 defaults
- 用户目录配置损坏 → 降级到内置配置
"""

import os
import json
import pytest


def test_load_json_config_user_first(temp_config_dirs):
    """用户配置存在时优先加载用户配置。"""
    from utils.config_loader import load_json_config

    user_dir, builtin_dir = temp_config_dirs

    # 用户目录：test_value_from_user
    # 内置目录：test_value_from_builtin
    _write_config(user_dir, "test_config", {"source": "user", "value": "from_user"})
    _write_config(
        builtin_dir, "test_config", {"source": "builtin", "value": "from_builtin"}
    )

    result = load_json_config("test_config", {"source": "defaults"})
    assert result["source"] == "user", "应优先加载用户配置"
    assert result["value"] == "from_user"


def test_load_json_config_fallback_to_builtin(temp_config_dirs):
    """仅有内置配置时加载内置配置。"""
    from utils.config_loader import load_json_config

    user_dir, builtin_dir = temp_config_dirs

    # 仅内置目录有配置
    _write_config(
        builtin_dir, "test_config", {"source": "builtin", "value": "from_builtin"}
    )

    result = load_json_config("test_config", {"source": "defaults"})
    assert result["source"] == "builtin", "应回退到内置配置"
    assert result["value"] == "from_builtin"


def test_load_json_config_all_missing_returns_defaults(temp_config_dirs):
    """均无配置文件时返回 defaults。"""
    from utils.config_loader import load_json_config

    result = load_json_config("nonexistent_config", {"source": "defaults", "key": 42})
    assert result["source"] == "defaults", "应返回 defaults"
    assert result["key"] == 42


def test_load_json_config_user_corrupted_fallback_to_builtin(temp_config_dirs):
    """用户配置解析失败时降级到内置配置。"""
    from utils.config_loader import load_json_config

    user_dir, builtin_dir = temp_config_dirs

    # 用户目录：损坏的 JSON
    _write_config(user_dir, "test_config", "这不是合法的 json{内容")
    # 内置目录：正常配置
    _write_config(
        builtin_dir, "test_config", {"source": "builtin", "value": "from_builtin"}
    )

    result = load_json_config("test_config", {"source": "defaults"})
    assert result["source"] == "builtin", "用户配置损坏应降级到内置配置"


# ============================================================================
# helpers
# ============================================================================


def _write_config(directory: str, name: str, data):
    """写入测试配置文件。"""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, ensure_ascii=False)
