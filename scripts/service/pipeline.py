"""
处理管道：编排文件查找 → 读取 → 清洗 → 合并 → 去重 → 输出全流程
"""

import os
import logging
import time
from typing import Callable

from core.reader import read_tenpay_trades
from core.processor import process_dataframe
from core.merger import merge_dataframes, deduplicate
from core.writer import write_excel

logger = logging.getLogger("TenpayMerge")


# ============================================================================
# 后处理分析（pipeline / CLI合并 / GUI合并 共享）
# ============================================================================

def post_merge_analysis(merged, progress=None) -> dict:
    """
    在去重后的 DataFrame 上运行停车识别 + 特殊交易筛选。

    被 pipeline.run()、bridge.py 合并路径、app_merge.py CLI 合并路径共享，
    确保三条执行路径行为一致。

    Args:
        merged: 去重后的 DataFrame
        progress: ProgressInfo 实例（可选），用于 GUI 日志

    Returns:
        {"parking_df": DataFrame|None, "special_df": DataFrame|None}
    """

    def _log(msg: str):
        logger.info(msg)
        if progress:
            progress.add_log(msg)

    # --- 停车缴费识别 ---
    parking_df = None
    try:
        from core.parking import load_parking_config, detect_parking_records, add_license_plate_column

        config = load_parking_config()
        parking_df = detect_parking_records(merged, config)
        if not parking_df.empty:
            parking_df = add_license_plate_column(parking_df, config['车牌省份简称'])
            _log(f"🅿️ 识别到 {len(parking_df)} 条停车缴费记录")
        else:
            _log("未识别到停车缴费记录")
    except Exception as e:
        logger.warning(f"停车缴费识别异常: {e}", exc_info=True)
        _log(f"⚠️ 停车缴费识别失败: {e}")

    # --- 特殊交易筛选 ---
    special_df = None
    try:
        from core.special_filter import load_special_filter_config, detect_special_records

        sf_config = load_special_filter_config()
        special_df = detect_special_records(merged, sf_config)
        if not special_df.empty:
            _log(f"💝 识别到 {len(special_df)} 条特殊交易记录")
        else:
            _log("未识别到特殊交易记录")
    except Exception as e:
        logger.warning(f"特殊交易筛选异常: {e}", exc_info=True)
        _log(f"⚠️ 特殊交易筛选失败: {e}")

    return {"parking_df": parking_df, "special_df": special_df}


class ProgressInfo:
    """进度信息"""

    def __init__(self):
        self.total = 0
        self.current = 0
        self.success = 0
        self.fail = 0
        self.skipped = 0
        self.status = "idle"  # idle / running / done / error
        self.logs: list[str] = []
        self.result: dict = {}

    def add_log(self, msg: str):
        self.logs.append(msg)
        # 保留最近200条日志
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "current": self.current,
            "success": self.success,
            "fail": self.fail,
            "skipped": self.skipped,
            "status": self.status,
            "logs": self.logs[-50:],  # 只返回最近50条
            "result": self.result,
        }


class TenpayPipeline:
    """单批次处理管道"""

    def __init__(
        self,
        source_dir: str,
        output_dir: str,
        output_name: str = "Tenpay_merge.xlsx",
        log_dir: str | None = None,
    ):
        self.source_dir = source_dir
        self.output_dir = output_dir
        self.output_name = output_name
        self.log_dir = log_dir or output_dir
        self.progress = ProgressInfo()

    def _find_txt_files(self) -> list[str]:
        """递归查找所有 TenpayTrades.txt 文件"""
        files = []
        for root, dirs, filenames in os.walk(self.source_dir):
            for fn in filenames:
                if fn == "TenpayTrades.txt":
                    files.append(os.path.join(root, fn))
        return files

    def _short_path(self, filepath: str) -> str:
        """生成短路径用于日志显示（取最后3级目录+文件名）"""
        parts = filepath.replace(self.source_dir, '').strip(os.path.sep).split(os.path.sep)
        if len(parts) >= 3:
            return os.path.join('...', *parts[-3:])
        return os.path.join(*parts)

    def run(self, progress_callback: Callable[[ProgressInfo], None] | None = None) -> dict:
        """
        执行完整处理管道

        Args:
            progress_callback: 进度回调函数，接收 ProgressInfo 对象

        Returns:
            {"output": str, "total": int, "success": int, "fail": int, "skipped": int, "rows": int}
        """
        start_time = time.time()

        # 1. 查找文件
        self.progress.status = "running"
        self.progress.add_log("正在扫描目录...")
        if progress_callback:
            progress_callback(self.progress)

        files = self._find_txt_files()
        self.progress.total = len(files)
        logger.info(f"找到 {len(files)} 个 TenpayTrades.txt 文件")

        if not files:
            self.progress.status = "error"
            self.progress.add_log("未找到任何 TenpayTrades.txt 文件")
            if progress_callback:
                progress_callback(self.progress)
            return {"output": "", "total": 0, "success": 0, "fail": 0, "skipped": 0, "rows": 0}

        # 2. 逐个处理
        dfs = []
        for i, filepath in enumerate(files):
            self.progress.current = i + 1
            short = self._short_path(filepath)

            # 读取
            df = read_tenpay_trades(filepath)
            if df is None:
                self.progress.skipped += 1
                continue

            # 清洗
            df = process_dataframe(df)
            if df is None or df.empty:
                self.progress.fail += 1
                self.progress.add_log(f"[FAIL] {short} - 处理失败")
                logger.warning(f"处理失败: {short}")
                if progress_callback:
                    progress_callback(self.progress)
                continue

            dfs.append(df)
            self.progress.success += 1
            self.progress.add_log(f"[OK] {short} - {len(df)} 行")
            logger.info(f"✔ {short} ({len(df)} 行)")

            if progress_callback:
                progress_callback(self.progress)

        # 3. 汇总
        if not dfs:
            self.progress.status = "error"
            self.progress.add_log("所有文件处理失败，无有效数据")
            if progress_callback:
                progress_callback(self.progress)
            return {
                "output": "",
                "total": self.progress.total,
                "success": 0,
                "fail": self.progress.fail,
                "skipped": self.progress.skipped,
                "rows": 0,
            }

        self.progress.add_log("正在合并数据...")
        if progress_callback:
            progress_callback(self.progress)

        merged = merge_dataframes(dfs)

        # 4. 去重
        self.progress.add_log(f"合并完成，共 {len(merged)} 行，正在进行去重...")
        if progress_callback:
            progress_callback(self.progress)

        merged = deduplicate(merged)

        # 4.5 停车缴费识别 + 特殊交易筛选（去重后进行）
        analysis = post_merge_analysis(merged, self.progress)
        parking_df = analysis["parking_df"]
        special_df = analysis["special_df"]

        # 5. 输出
        output_path = os.path.join(self.output_dir, self.output_name)
        write_excel(merged, output_path, parking_df=parking_df, special_df=special_df)

        elapsed = time.time() - start_time
        self.progress.status = "done"
        self.progress.add_log(f"✅ 完成! 耗时 {elapsed:.1f} 秒")
        self.progress.add_log(f"📊 总记录: {len(merged)} 行 | 成功: {self.progress.success} 文件 | "
                              f"失败: {self.progress.fail} | 跳过: {self.progress.skipped}")

        self.progress.result = {
            "output": output_path,
            "total": self.progress.total,
            "success": self.progress.success,
            "fail": self.progress.fail,
            "skipped": self.progress.skipped,
            "rows": len(merged),
            "elapsed": round(elapsed, 1),
            "parking_rows": len(parking_df) if parking_df is not None else 0,
        }

        logger.info(f"管道完成: {self.progress.result}")

        if progress_callback:
            progress_callback(self.progress)

        return self.progress.result
