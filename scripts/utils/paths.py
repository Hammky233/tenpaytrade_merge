"""
路径工具 — 兼容开发环境和 PyInstaller --onefile 打包

在 PyInstaller 打包后，sys._MEIPASS 指向临时解压目录，
而开发环境中 __file__ 指向真实文件路径。
"""

import os
import sys


def get_scripts_dir() -> str:
    """
    获取 scripts/ 目录的绝对路径。

    兼容两种环境：
    - 开发环境：基于此文件的 __file__ 推算（scripts/utils/paths.py → scripts/）
    - PyInstaller：基于 sys._MEIPASS + 'scripts'

    Returns:
        scripts/ 目录的绝对路径
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller --onefile 打包后
        return os.path.join(sys._MEIPASS, 'scripts')
    else:
        # 开发环境：paths.py 位于 scripts/utils/，向上两级为 scripts/
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_config_dir() -> str:
    """
    获取 config/ 目录的绝对路径。

    Returns:
        scripts/config/ 目录的绝对路径
    """
    return os.path.join(get_scripts_dir(), 'config')


def find_files_by_name(source_dir: str, filename: str) -> list[str]:
    """
    递归扫描 source_dir 下所有文件名为 filename 的文件。

    结果按路径排序，确保确定性输出。

    Args:
        source_dir: 扫描根目录
        filename: 目标文件名（精确匹配），如 "TenpayTrades.txt"

    Returns:
        文件路径列表（按路径排序）
    """
    files = []
    for root, dirs, filenames in os.walk(source_dir):
        for fn in filenames:
            if fn == filename:
                files.append(os.path.join(root, fn))
    files.sort()
    return files
