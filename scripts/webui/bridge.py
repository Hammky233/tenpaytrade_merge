"""
pywebview Bridge API — Python 端暴露给前端的方法
"""

import os
import sys
import threading
from tkinter import filedialog

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.pipeline import TenpayPipeline, ProgressInfo
from core.merger import merge_dataframes, deduplicate
from core.writer import write_excel
import pandas as pd


class Api:
    """pywebview JS-Python Bridge"""

    def __init__(self):
        self._pipeline: TenpayPipeline | None = None
        self._thread: threading.Thread | None = None

    def select_folder(self) -> str:
        """打开文件夹选择对话框，返回所选路径（取消返回空字符串）"""
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title="选择文件夹")
        root.destroy()
        return folder or ""

    def select_file(self, file_types: str = "Excel files (*.xlsx)|*.xlsx") -> str:
        """打开文件选择对话框，返回所选路径（取消返回空字符串）"""
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        filepath = filedialog.askopenfilename(
            title="选择文件",
            filetypes=[(ft.split('|')[0], ft.split('|')[1]) for ft in file_types.split(';')] if file_types else None,
        )
        root.destroy()
        return filepath or ""

    def select_files(self, file_types: str = "Excel files (*.xlsx)|*.xlsx") -> str:
        """多文件选择，返回用 | 分隔的路径字符串"""
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        files = filedialog.askopenfilenames(
            title="选择文件（可多选）",
            filetypes=[(ft.split('|')[0], ft.split('|')[1]) for ft in file_types.split(';')] if file_types else None,
        )
        root.destroy()
        return "|".join(files) if files else ""

    def start_batch_process(self, source: str, output: str, output_name: str = "Tenpay_merge.xlsx") -> str:
        """
        启动单批次处理（后台线程），返回 "started" 或错误信息
        """
        if self._thread and self._thread.is_alive():
            return "已有任务正在运行"
        if not source:
            return "请先选择数据源文件夹"
        if not output:
            return "请先选择输出文件夹"

        self._pipeline = TenpayPipeline(
            source_dir=source,
            output_dir=output,
            output_name=output_name,
        )

        def _run():
            self._pipeline.run()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        return "started"

    def get_batch_status(self) -> dict:
        """获取单批次处理进度"""
        if self._pipeline:
            return self._pipeline.progress.to_dict()
        return {"status": "idle", "logs": []}

    def start_merge_process(self, input_files_str: str, output: str) -> str:
        """
        启动多批次合并（后台线程）
        input_files_str: 用 | 分隔的文件路径
        """
        if self._thread and self._thread.is_alive():
            return "已有任务正在运行"
        if not input_files_str:
            return "请先选择待合并的文件"

        files = [f for f in input_files_str.split("|") if f.strip()]
        if not files:
            return "文件列表为空"

        # 使用 pipeline 的 progress 来传递状态
        self._pipeline = TenpayPipeline(
            source_dir="",  # 合并模式不需要 source
            output_dir=os.path.dirname(output) or ".",
            output_name=os.path.basename(output),
        )
        self._pipeline.progress.total = len(files)

        def _run():
            progress = self._pipeline.progress
            progress.status = "running"
            progress.add_log(f"开始合并 {len(files)} 个批次文件...")

            try:
                dfs = []
                for i, f in enumerate(files):
                    progress.current = i + 1
                    fname = os.path.basename(f)
                    progress.add_log(f"读取: {fname}")
                    df = pd.read_excel(f, dtype=str)
                    dfs.append(df)
                    progress.add_log(f"  → {len(df)} 行")
                    progress.success += 1

                progress.add_log("合并中...")
                merged = merge_dataframes(dfs)
                before = len(merged)

                merged = deduplicate(merged)
                after = len(merged)

                # 停车缴费识别
                parking_df = None
                try:
                    from core.parking import load_parking_config, detect_parking_records, add_license_plate_column

                    config = load_parking_config()
                    parking_df = detect_parking_records(merged, config)
                    if not parking_df.empty:
                        parking_df = add_license_plate_column(parking_df, config['车牌省份简称'])
                        progress.add_log(f"🅿️ 识别到 {len(parking_df)} 条停车缴费记录")
                    else:
                        progress.add_log("未识别到停车缴费记录")
                except Exception as e:
                    progress.add_log(f"⚠️ 停车缴费识别失败: {e}")

                write_excel(merged, output, parking_df=parking_df)

                progress.status = "done"
                progress.add_log(f"✅ 合并完成!")
                progress.add_log(f"合并前: {before} 行 → 去重后: {after} 行 (移除 {before - after} 条)")
                progress.result = {"output": output, "rows": after, "removed": before - after}

            except Exception as e:
                progress.status = "error"
                progress.add_log(f"❌ 合并失败: {e}")

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        return "started"

    def get_file_info(self, filepath: str) -> dict:
        """获取单个 xlsx 文件的基本信息（行数、列数）"""
        try:
            df = pd.read_excel(filepath, nrows=0)
            cols = len(df.columns)
            import openpyxl
            wb = openpyxl.load_workbook(filepath, read_only=True)
            ws = wb.active
            rows = ws.max_row - 1  # 减去表头
            wb.close()
            return {"rows": rows, "cols": cols, "filename": os.path.basename(filepath)}
        except Exception as e:
            return {"rows": 0, "cols": 0, "filename": os.path.basename(filepath), "error": str(e)}

    def stop_process(self) -> str:
        """停止当前任务（仅标记，线程会自然结束）"""
        if self._pipeline:
            self._pipeline.progress.status = "idle"
            return "stopped"
        return "no task running"
