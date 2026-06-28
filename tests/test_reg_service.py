"""
测试 scripts/service/reg_service.py 注册信息处理服务。

覆盖场景：
  - 含有效注册信息文件的目录 → 返回统计 dict
  - 无文件的目录 → 返回 None
"""

import os
import pytest

# 最小有效注册信息样本（Tab 分隔）
_SAMPLE_REG_HEADER = (
    "账户状态\t账号\t注册姓名\t注册身份证号\t注册时间\t绑定手机\t绑定状态\t开户行信息\t银行账号"
)
_SAMPLE_REG_ROWS = [
    "正常\tU001\t张三\t440000000000000000\t2020-01-01\t13800138000\t已绑定\t某银行\t6222000000000000",
]


def _write_reg_file(directory: str, filename: str, lines: list[str]) -> str:
    """将注册信息行写入 UTF-8 文件，返回完整路径。"""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    content = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestRunRegProcess:
    """run_reg_process 全流程测试。"""

    def test_with_valid_file_returns_stats(self, tmp_path):
        """含有效注册信息文件的目录返回统计 dict。"""
        from service.reg_service import run_reg_process

        # 在 tmp_path 下创建带 TenpayRegInfo.txt 的子目录
        batch_dir = tmp_path / "batch1"
        _write_reg_file(str(batch_dir), "TenpayRegInfo.txt", [_SAMPLE_REG_HEADER] + _SAMPLE_REG_ROWS)

        result = run_reg_process(str(tmp_path), str(tmp_path))
        assert result is not None, "含有效文件时应返回统计"
        assert result["success"] == 1
        assert result["files"] == 1
        assert result["fail"] == 0
        assert result["basic_rows"] >= 1

        # 验证输出了 xlsx 文件
        xlsx_files = list(tmp_path.glob("TenpayRegInfo_merge*.xlsx"))
        assert len(xlsx_files) > 0, "应生成注册信息 Excel 文件"
        assert result["output"] != "", "output 不应为空"

    def test_with_valid_file_callback_receives_logs(self, tmp_path):
        """progress_callback 正常接收日志。"""
        from service.reg_service import run_reg_process

        batch_dir = tmp_path / "batch1"
        _write_reg_file(str(batch_dir), "TenpayRegInfo.txt", [_SAMPLE_REG_HEADER] + _SAMPLE_REG_ROWS)

        received = []

        def _cb(msg: str):
            received.append(msg)

        result = run_reg_process(str(tmp_path), str(tmp_path), progress_callback=_cb)
        assert result is not None
        assert len(received) > 0, "回调应收到日志"
        assert any("开始清洗注册信息" in msg for msg in received), "日志应包含开始标记"
        assert any("注册信息清洗完成" in msg for msg in received), "日志应包含完成标记"

    def test_no_files_returns_none(self, tmp_path):
        """无文件时返回 None。"""
        from service.reg_service import run_reg_process

        result = run_reg_process(str(tmp_path), str(tmp_path))
        assert result is None

    def test_empty_directory_returns_none(self, tmp_path):
        """空目录返回 None。"""
        from service.reg_service import run_reg_process

        os.makedirs(tmp_path / "empty", exist_ok=True)
        result = run_reg_process(str(tmp_path), str(tmp_path))
        assert result is None

    def test_timestamp_applied_to_filename(self, tmp_path):
        """传入 timestamp 时输出文件名包含时间戳。"""
        from service.reg_service import run_reg_process

        batch_dir = tmp_path / "batch1"
        _write_reg_file(str(batch_dir), "TenpayRegInfo.txt", [_SAMPLE_REG_HEADER] + _SAMPLE_REG_ROWS)

        result = run_reg_process(str(tmp_path), str(tmp_path), timestamp="0601_1430")
        assert result is not None

        expected_name = f"TenpayRegInfo_merge_0601_1430.xlsx"
        expected_path = os.path.join(str(tmp_path), expected_name)
        assert os.path.isfile(expected_path), f"应生成带时间戳的文件: {expected_path}"
