"""
注册信息处理服务 — 编排 TenpayRegInfo.txt 的扫描、解析、合并和输出

职责：
  - 扫描数据源目录中的 TenpayRegInfo.txt
  - 逐文件解析、清洗合并
  - 提取人员基础信息
  - 输出 Excel

与桥接层解耦：
  - 不依赖 pywebview 或 threading
  - 通过可选的 progress_callback 向调用方反馈日志
"""

import os
import time
import logging

logger = logging.getLogger("TenpayMerge")


def run_reg_process(source: str, output: str, timestamp: str = "",
                    progress_callback=None) -> dict | None:
    """
    执行注册信息清洗全流程。

    Args:
        source: 数据源文件夹
        output: 输出文件夹
        timestamp: 时间戳（MMDD_HHmm），用于文件名后缀
        progress_callback: 可选回调，接收日志字符串用于 GUI 反馈

    Returns:
        dict 包含处理结果统计，或无文件时返回 None
    """
    from core.reg_reader import read_tenpay_reg_info
    from core.reg_processor import process_reg_data, build_person_info
    from core.writer import write_reg_excel
    from utils.paths import find_files_by_name

    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log("─" * 40)
    _log("📋 开始清洗注册信息...")

    # 1. 扫描 TenpayRegInfo.txt 文件
    reg_files = find_files_by_name(source, "TenpayRegInfo.txt")

    if not reg_files:
        _log("⚠️ 未找到 TenpayRegInfo.txt 文件，跳过注册信息清洗")
        return None

    _log(f"扫描到 {len(reg_files)} 个 TenpayRegInfo.txt 文件")

    t_start = time.time()

    # 2. 逐文件解析
    success = 0
    fail = 0
    skipped = 0
    records = []

    for i, filepath in enumerate(reg_files, 1):
        try:
            rel_path = os.path.relpath(filepath, source)
        except ValueError:
            rel_path = filepath

        try:
            result = read_tenpay_reg_info(filepath)
            if result is None:
                skipped += 1
            else:
                records.append(result)
                success += 1
        except Exception as e:
            fail += 1
            _log(f"[{i}/{len(reg_files)}] 失败: {rel_path} — {e}")

    # 3. 清洗合并
    basic_df, changes_df = process_reg_data(records)

    # 4. 提取人员基础信息
    person_df = build_person_info(basic_df)

    # 5. 输出 Excel
    reg_name = f"TenpayRegInfo_merge_{timestamp}.xlsx" if timestamp else "TenpayRegInfo_merge.xlsx"
    output_path = os.path.join(output, reg_name)
    result_path = write_reg_excel(basic_df, changes_df, output_path, person_df=person_df)

    elapsed = time.time() - t_start

    # 6. 日志摘要
    _log(f"✅ 注册信息清洗完成!")
    _log(f"文件总数: {len(reg_files)} | 成功: {success} | 失败: {fail} | 跳过: {skipped}")
    _log(f"注册信息汇总: {len(basic_df)} 条 | 变更记录: {len(changes_df)} 条 | "
         f"基础信息(自然人): {len(person_df)} 人")
    _log(f"耗时: {elapsed:.1f} 秒")
    if result_path:
        _log(f"输出文件: {result_path}")
    else:
        _log("⚠️ 注册信息输出为空（无有效数据）")

    return {
        "output": result_path or "",
        "basic_rows": len(basic_df),
        "changes_rows": len(changes_df),
        "person_rows": len(person_df),
        "files": len(reg_files),
        "success": success,
        "fail": fail,
        "skipped": skipped,
        "elapsed": round(elapsed, 1),
    }
