"""
编译检查 — 确保所有源文件无语法错误

每次新增或修改源文件后，语法错误可能被 pytest 漏检（如果该文件未被任何测试导入）。
此文件通过 py_compile 检查 scripts/ 下所有 .py 文件，确保基本可编译。
"""

import py_compile
import pytest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _iter_source_files():
    """递归遍历 scripts/ 下所有 .py 文件（不含 __pycache__）。"""
    for py_file in sorted(SCRIPTS_DIR.rglob("*.py")):
        # 跳过 __pycache__ 下的文件
        if "__pycache__" in py_file.parts:
            continue
        yield py_file


class TestCompile:
    """确保 scripts/ 下所有源文件可通过 py_compile 编译。"""

    def test_all_scripts_compile(self):
        """每个 .py 文件应能成功编译。"""
        errors = []
        for py_file in _iter_source_files():
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(f"{py_file.relative_to(SCRIPTS_DIR.parent)}: {e}")

        if errors:
            pytest.fail("\n".join(errors))
