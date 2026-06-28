"""
测试 scripts/utils/paths.py 路径工具。

覆盖以下场景：
- get_config_dir() 在开发环境返回 scripts/config/
- get_user_config_dir() 在开发环境与 get_config_dir() 相同
- get_user_config_dir() 在模拟打包环境下返回 APPDATA 路径
"""

import os
import sys
import pytest


def test_get_config_dir_resolved():
    """get_config_dir() 应指向 scripts/config/ 目录。"""
    from utils.paths import get_config_dir

    config_dir = get_config_dir()
    assert os.path.isabs(config_dir), "config_dir 应为绝对路径"
    assert config_dir.endswith("scripts" + os.sep + "config") or config_dir.endswith(
        "scripts/config"
    ), f"config_dir 应以 scripts/config 结尾: {config_dir}"


def test_get_user_config_dir_dev_matches_config_dir():
    """开发环境下 get_user_config_dir() 应与 get_config_dir() 相同。"""
    from utils.paths import get_config_dir, get_user_config_dir

    # 确保不是在 frozen 环境（测试在开发环境运行）
    assert not getattr(sys, "frozen", False), "测试应在非打包环境运行"

    assert (
        get_user_config_dir() == get_config_dir()
    ), "开发环境下用户配置目录应与内置配置目录相同"


def test_get_user_config_dir_frozen_uses_appdata(monkeypatch):
    """
    模拟 PyInstaller 打包环境时，get_user_config_dir() 应返回 APPDATA 下的路径。
    """
    import utils.paths as paths_mod

    # 模拟 sys.frozen = True
    monkeypatch.setattr(paths_mod.sys, "frozen", True, raising=False)

    # 设置固定的 APPDATA 环境变量
    test_appdata = "C:\\Users\\TestUser\\AppData\\Roaming"
    monkeypatch.setenv("APPDATA", test_appdata)

    user_dir = paths_mod.get_user_config_dir()
    expected = os.path.join(test_appdata, "tenpaytrade", "config")
    assert (
        user_dir == expected
    ), f"打包环境下应返回 {expected}，实际得到 {user_dir}"


def test_get_user_config_dir_frozen_fallback_on_no_appdata(monkeypatch):
    """
    模拟打包环境且 APPDATA 不存在时，应 fallback 到 expanduser('~')。
    """
    import utils.paths as paths_mod

    monkeypatch.setattr(paths_mod.sys, "frozen", True, raising=False)
    monkeypatch.delenv("APPDATA", raising=False)

    user_dir = paths_mod.get_user_config_dir()
    expected = os.path.join(os.path.expanduser("~"), "tenpaytrade", "config")
    assert (
        user_dir == expected
    ), f"无 APPDATA 时应 fallback 到 {expected}，实际得到 {user_dir}"
