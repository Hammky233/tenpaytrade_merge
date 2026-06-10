"""
pywebview Bridge API — Python 端暴露给前端的方法
"""

import os
import sys
import threading

# tkinter 在部分 Linux 发行版需要单独安装 python3-tk
try:
    from tkinter import filedialog
    _TKINTER_AVAILABLE = True
except ImportError:
    _TKINTER_AVAILABLE = False

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.pipeline import TenpayPipeline, ProgressInfo, post_merge_analysis
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
        if not _TKINTER_AVAILABLE:
            return self._fallback_dialog_error()
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title="选择文件夹")
        root.destroy()
        return folder or ""

    def select_file(self, file_types: str = "Excel files (*.xlsx)|*.xlsx") -> str:
        """打开文件选择对话框，返回所选路径（取消返回空字符串）"""
        if not _TKINTER_AVAILABLE:
            return self._fallback_dialog_error()
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
        if not _TKINTER_AVAILABLE:
            return self._fallback_dialog_error()
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

    def _fallback_dialog_error(self) -> str:
        """tkinter 不可用时的错误提示（Linux 需安装 python3-tk）"""
        import platform
        msg = "文件对话框不可用：tkinter 未安装"
        if platform.system() == "Linux":
            msg += "。请运行: sudo apt install python3-tk (或等效命令)"
        return f"__ERROR__:{msg}"

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
            try:
                self._pipeline.run()
            except Exception as e:
                import traceback
                self._pipeline.progress.status = "error"
                self._pipeline.progress.add_log(f"❌ 处理异常: {e}")
                # 将完整堆栈也写入日志，方便排查
                for line in traceback.format_exc().splitlines():
                    if line.strip():
                        self._pipeline.progress.add_log(f"   {line.strip()}")

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

                # 停车缴费识别 + 特殊交易筛选（通过共享函数，与 pipeline 行为一致）
                analysis = post_merge_analysis(merged)
                parking_df = analysis["parking_df"]
                special_df = analysis["special_df"]

                write_excel(merged, output, parking_df=parking_df, special_df=special_df)

                progress.status = "done"
                progress.add_log(f"✅ 合并完成!")
                progress.add_log(f"合并前: {before} 行 → 去重后: {after} 行 (移除 {before - after} 条)")
                progress.result = {"output": output, "rows": after, "removed": before - after}

            except Exception as e:
                import traceback
                progress.status = "error"
                progress.add_log(f"❌ 合并失败: {e}")
                for line in traceback.format_exc().splitlines():
                    if line.strip():
                        progress.add_log(f"   {line.strip()}")

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

    def get_parking_config(self) -> dict:
        """获取停车缴费识别配置"""
        from core.parking import load_parking_config
        try:
            return load_parking_config()
        except Exception as e:
            return {"error": str(e)}

    def save_parking_config(self, config: dict) -> str:
        """保存停车缴费识别配置到 JSON 文件，返回 "ok" 或错误信息"""
        import json

        # 验证必填字段
        required_fields = ["备注2关键词", "排除关键词", "对手侧账户名称关键词", "车牌省份简称"]
        for field in required_fields:
            if field not in config:
                return f"缺少必填字段: {field}"
            if not isinstance(config[field], list):
                return f"字段 {field} 必须是数组"

        try:
            from utils.paths import get_config_dir
            config_path = os.path.join(get_config_dir(), "parking_config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return "ok"
        except Exception as e:
            return f"保存失败: {e}"

    def get_time_period_config(self) -> dict:
        """获取时段分类配置"""
        from core.processor import load_time_period_config
        try:
            return load_time_period_config()
        except Exception as e:
            return {"error": str(e)}

    def save_time_period_config(self, config: dict) -> str:
        """保存时段分类配置到 JSON 文件，返回 "ok" 或错误信息"""
        import json

        # 验证必填字段
        if "时段" not in config or not isinstance(config["时段"], list):
            return "缺少必填字段: 时段"
        for period in config["时段"]:
            if not all(k in period for k in ("name", "start", "end")):
                return "每个时段必须包含 name, start, end"

        try:
            from utils.paths import get_config_dir
            config_path = os.path.join(get_config_dir(), "time_period_config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return "ok"
        except Exception as e:
            return f"保存失败: {e}"
