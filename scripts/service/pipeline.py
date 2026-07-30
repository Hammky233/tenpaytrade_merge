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

def post_merge_analysis(merged, progress=None,
                        api_key=None, existing_location_map=None) -> dict:
    """
    在去重后的 DataFrame 上运行停车识别 + 特殊交易筛选 + 疑似麻友识别 + 群红包识别。

    被 pipeline.run()、bridge.py 合并路径、app_merge.py CLI 合并路径共享，
    确保三条执行路径行为一致。

    Args:
        merged: 去重后的 DataFrame
        progress: ProgressInfo 实例（可选），用于 GUI 日志
        api_key: DeepSeek API Key（可选），非空时启用地点识别
        existing_location_map: dict{备注2文本: 地点}（可选），多批次合并时恢复既往地点

    Returns:
        {"parking_df": DataFrame|None, "special_df": DataFrame|None,
         "mahjong_df": DataFrame|None, "mahjong_stats_df": DataFrame|None,
         "mahjong_circle_stats_df": DataFrame|None,
         "grp_df": DataFrame|None, "grp_stats_df": DataFrame|None}
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

    # --- 地点识别（停车缴费）---
    if api_key and parking_df is not None and not parking_df.empty:
        try:
            from core.location import extract_locations
            parking_df = extract_locations(
                parking_df, api_key,
                existing_locations=existing_location_map,
                progress_callback=lambda msg: _log(msg),
            )
        except Exception as e:
            logger.warning(f"地点提取异常: {e}", exc_info=True)
            _log(f"⚠️ 地点提取失败: {e}")

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

    # --- 疑似麻友识别 ---
    mahjong_df = None
    mahjong_stats_df = None
    mahjong_circle_stats_df = None
    try:
        from core.mahjong import load_mahjong_config, detect_mahjong_records

        mj_config = load_mahjong_config()
        mahjong_df, mahjong_stats_df, mahjong_circle_stats_df = detect_mahjong_records(merged, mj_config)
        if not mahjong_df.empty:
            _log(f"🀄 识别到 {len(mahjong_stats_df)} 名疑似麻友, "
                 f"{len(mahjong_circle_stats_df)} 个疑似圈子, 涉及 {len(mahjong_df)} 条交易记录")
        else:
            _log("未识别到疑似麻友记录")
    except Exception as e:
        logger.warning(f"疑似麻友识别异常: {e}", exc_info=True)
        _log(f"⚠️ 疑似麻友识别失败: {e}")

    # --- 群红包识别 ---
    grp_df = None
    grp_stats_df = None
    try:
        from core.group_red_packet import detect_group_red_packet_records

        grp_df, grp_stats_df = detect_group_red_packet_records(merged)
        if not grp_df.empty:
            _log(f"🧧 识别到 {len(grp_df)} 条群红包记录, "
                 f"涉及 {len(grp_stats_df)} 个对手方")
        else:
            _log("未识别到群红包记录")
    except Exception as e:
        logger.warning(f"群红包识别异常: {e}", exc_info=True)
        _log(f"⚠️ 群红包识别失败: {e}")

    return {"parking_df": parking_df, "special_df": special_df,
            "mahjong_df": mahjong_df, "mahjong_stats_df": mahjong_stats_df,
            "mahjong_circle_stats_df": mahjong_circle_stats_df,
            "grp_df": grp_df, "grp_stats_df": grp_stats_df}


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
        api_key: str | None = None,
    ):
        self.source_dir = source_dir
        self.output_dir = output_dir
        self.output_name = output_name
        self.log_dir = log_dir or output_dir
        self.api_key = api_key
        self.progress = ProgressInfo()

    def _find_txt_files(self) -> list[str]:
        """递归查找所有 TenpayTrades.txt 文件"""
        from utils.paths import find_files_by_name
        return find_files_by_name(self.source_dir, "TenpayTrades.txt")

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

        # 4.5 停车缴费识别 + 特殊交易筛选 + 疑似麻友识别 + 群红包识别（去重后进行）
        analysis = post_merge_analysis(merged, self.progress, api_key=self.api_key)
        parking_df = analysis["parking_df"]
        special_df = analysis["special_df"]
        mahjong_df = analysis.get("mahjong_df")
        mahjong_stats_df = analysis.get("mahjong_stats_df")
        mahjong_circle_stats_df = analysis.get("mahjong_circle_stats_df")
        grp_df = analysis.get("grp_df")
        grp_stats_df = analysis.get("grp_stats_df")

        # 5. 输出
        output_path = os.path.join(self.output_dir, self.output_name)
        try:
            result_path = write_excel(merged, output_path,
                        parking_df=parking_df, special_df=special_df,
                        mahjong_df=mahjong_df, mahjong_stats_df=mahjong_stats_df,
                        mahjong_circle_stats_df=mahjong_circle_stats_df,
                        grp_df=grp_df, grp_stats_df=grp_stats_df)
        except Exception as _we:
            import traceback
            _we_detail = traceback.format_exc()
            logger.error(f"write_excel 调用异常: {_we}\n{_we_detail}")
            self.progress.add_log(f"❌ Excel 输出异常: {_we}")
            raise

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
            "mahjong_people": len(mahjong_stats_df) if mahjong_stats_df is not None else 0,
            "mahjong_rows": len(mahjong_df) if mahjong_df is not None else 0,
            "mahjong_circles": len(mahjong_circle_stats_df) if mahjong_circle_stats_df is not None else 0,
            "grp_rows": len(grp_df) if grp_df is not None else 0,
            "grp_people": len(grp_stats_df) if grp_stats_df is not None else 0,
        }

        logger.info(f"管道完成: {self.progress.result}")

        if progress_callback:
            progress_callback(self.progress)

        return self.progress.result
