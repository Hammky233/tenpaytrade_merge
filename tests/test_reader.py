"""
测试 scripts/core/reader.py 文件读取。

覆盖以下场景：
- 小样本有效文件（< 1KB 但含数据行）可以被读取
- 仅表头行（无数据行）返回 None
- 空文件返回 None
- 仅含空行的文件返回 None
"""

import os
import pytest


# 典型交易文件的表头（Tab 分隔）
_SAMPLE_HEADER = (
    "交易时间\t交易用途类型\t借贷类型\t交易金额(分)\t用户ID\t"
    "交易单号\t大单号\t备注1\t备注2\t对手方ID\t"
    "对手方接收金额(元)\t用户侧账号名称\t对手侧账户名称"
)

# 2 行有效交易数据
_SAMPLE_ROWS = [
    "2026/4/2 14:30:00\t消费\t出\t5000\tU001\tT001\tB001\t\t停车缴费\tP001\t50.0\t用户A\t停车场Y",
    "2026/4/5 0:05:00\t红包\t出\t100\tU001\tT004\tB004\t微信红包\t\tP004\t0.50\t用户A\t朋友D",
]


def _write_trades_file(directory: str, filename: str, lines: list[str]) -> str:
    """将交易行写入 utf-8 文件，返回完整路径。"""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    content = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_read_small_valid_file(tmp_path):
    """
    小于 1KB 但包含有效数据行的文件应被正常读取。
    表头 + 2 行数据通常 < 500 字节，远小于 1KB。
    """
    from core.reader import read_tenpay_trades

    lines = [_SAMPLE_HEADER] + _SAMPLE_ROWS
    filepath = _write_trades_file(str(tmp_path), "TenpayTrades.txt", lines)

    # 验证文件确实小于 1KB
    size = os.path.getsize(filepath)
    assert size < 1024, f"测试数据应小于 1KB，实际 {size}B"

    df = read_tenpay_trades(filepath)
    assert df is not None, "含有效数据的小文件不应返回 None"
    assert len(df) == 2, f"应读取 2 行数据，实际 {len(df)}"


def test_read_file_with_only_header(tmp_path):
    """仅含表头行、无数据行的文件应返回 None。"""
    from core.reader import read_tenpay_trades

    filepath = _write_trades_file(str(tmp_path), "TenpayTrades.txt", [_SAMPLE_HEADER])

    df = read_tenpay_trades(filepath)
    assert df is None, "仅表头的文件应返回 None"


def test_read_empty_file(tmp_path):
    """完全空文件（0 字节）应返回 None。"""
    from core.reader import read_tenpay_trades

    filepath = _write_trades_file(str(tmp_path), "TenpayTrades.txt", [""])

    df = read_tenpay_trades(filepath)
    assert df is None, "空文件应返回 None"


def test_read_file_with_only_blank_lines(tmp_path):
    """仅含空行和表头、无有效数据行的文件应返回 None。"""
    from core.reader import read_tenpay_trades

    lines = [_SAMPLE_HEADER, "", "  ", ""]
    filepath = _write_trades_file(str(tmp_path), "TenpayTrades.txt", lines)

    df = read_tenpay_trades(filepath)
    assert df is None, "仅表头+空行的文件应返回 None"
