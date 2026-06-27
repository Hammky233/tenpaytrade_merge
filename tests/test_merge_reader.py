"""
多批次合并读取测试 — scripts/app_merge.py / scripts/webui/bridge.py

测试 pd.read_excel 指定 sheet_name 的行为：
- 目标工作表不在第一个位置时仍能正确读取
- 缺少目标工作表时抛出 ValueError
"""

import os
import tempfile

import pandas as pd
import pytest


def _make_multi_sheet_excel(tmpdir: str, sheets: dict, filename: str = "test.xlsx"):
    """
    构造一个包含多个工作表的 Excel 文件。
    sheets: {sheet_name: DataFrame}
    返回完整文件路径。
    """
    path = os.path.join(tmpdir, filename)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    return path


class TestReadTargetSheet:
    """读取指定工作表 — 多工作表场景。"""

    def test_read_target_sheet_not_first(self):
        """
        目标工作表「财付通交易汇总」在第二个位置时，
        指定 sheet_name 应正确读取其数据，而不是第一个工作表的数据。
        """
        other_data = pd.DataFrame({"无关列": ["A", "B"]})
        target_data = pd.DataFrame({
            "交易时间": ["2025-01-01 08:30:00", "2025-01-02 12:00:00"],
            "金额": ["100", "200"],
        })

        sheets = {
            "其他工作表": other_data,
            "财付通交易汇总": target_data,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_multi_sheet_excel(tmpdir, sheets)

            # 指定 sheet_name 读取
            result = pd.read_excel(path, sheet_name="财付通交易汇总", dtype=str)

            # 验证读的是目标工作表数据，不是第一个工作表
            assert len(result) == 2
            assert list(result.columns) == ["交易时间", "金额"]
            assert result.iloc[0]["交易时间"] == "2025-01-01 08:30:00"
            assert result.iloc[1]["金额"] == "200"

    def test_missing_target_sheet_raises(self):
        """
        文件缺少「财付通交易汇总」工作表时，
        pd.read_excel 应抛出 ValueError。
        """
        sheets = {
            "工作表A": pd.DataFrame({"A": [1]}),
            "工作表B": pd.DataFrame({"B": [2]}),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_multi_sheet_excel(tmpdir, sheets)

            with pytest.raises(ValueError):
                pd.read_excel(path, sheet_name="财付通交易汇总", dtype=str)

    def test_sheet_at_first_position(self):
        """
        目标工作表在第一个位置时，行为与修改前一致（回归）。
        """
        data = pd.DataFrame({
            "交易时间": ["2025-03-01 10:00:00"],
            "金额": ["300"],
        })

        sheets = {"财付通交易汇总": data}

        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_multi_sheet_excel(tmpdir, sheets)

            result = pd.read_excel(path, sheet_name="财付通交易汇总", dtype=str)

            assert len(result) == 1
            assert result.iloc[0]["金额"] == "300"

    def test_all_files_missing_target_gets_empty(self):
        """
        所有输入文件均缺少「财付通交易汇总」时，
        模拟 GUI 循环收集结果应为空列表，merge 后应为空 DataFrame，
        write 后应返回空字符串（即不会错误地"合并完成"）。
        """
        df_a = pd.DataFrame({"A": [1]})
        df_b = pd.DataFrame({"B": [2]})

        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = _make_multi_sheet_excel(tmpdir, {"工作表X": df_a}, filename="a.xlsx")
            path2 = _make_multi_sheet_excel(tmpdir, {"工作表Y": df_b}, filename="b.xlsx")

            # 模拟 GUI 合并循环：读取所有文件，缺少目标 sheet 时跳过
            dfs = []
            errors = 0
            for f in [path1, path2]:
                try:
                    df = pd.read_excel(f, sheet_name="财付通交易汇总", dtype=str)
                    dfs.append(df)
                except ValueError:
                    errors += 1

            # 两个文件都应失败
            assert errors == 2
            assert len(dfs) == 0

            # merge 空列表 → 空 DataFrame（无有用输出）
            from core.merger import merge_dataframes
            from core.writer import write_excel
            merged = merge_dataframes(dfs)
            assert len(merged) == 0

            # write 空 DataFrame → 空字符串（不会写出无意义文件）
            output_path = os.path.join(tmpdir, "merged.xlsx")
            result = write_excel(merged, output_path)
            assert result == ""
