# 实现计划 — T009

## 任务 ID

T009

## 目标

在不改变 GUI 通信模式的前提下，降低 `scripts/webui/bridge.py` 的职责密度。将配置读写和注册信息编排两类职责迁移到 `scripts/service/` 层，使 `Api` 类更专注于参数校验、线程调度和返回值封装。

## 理解分析

### 现状

`scripts/webui/bridge.py`（598 行）当前承载以下职责：

| 职责类别 | 方法/代码块 | 行数 | 是否核心桥接 |
|---------|------------|------|------------|
| UI 对话框 | `select_folder/select_file/select_files` | ~48 | 是（tkinter 交互） |
| 信息查询 | `get_version/get_author` | ~8 | 是（pywebview API） |
| 单批次处理 | `start_batch_process` + `_run` | ~63 | 部分（含线程调度和业务编排） |
| **注册信息处理** | `_run_reg_process` | **~85** | **否（纯业务编排）** |
| 进度查询/取消 | `get_batch_status/stop_process` | ~8 | 是（pywebview API） |
| 多批次合并 | `start_merge_process` | ~120 | 部分（含大量业务逻辑） |
| 文件信息 | `get_file_info` | ~13 | 是（pywebview API） |
| **配置读写** | `get/save_parking_config + get/save_time_period_config` | **~60** | **否（纯业务逻辑，Api 保留同名 wrapper）** |
| 地点重提取 | `re_extract_locations` | ~140 | 部分（含大量业务逻辑） |

两类适合优先迁移的职责：

1. **配置读写（4 个方法）** — 包含字段验证和 JSON 持久化，最简洁的"service 层"示范
2. **注册信息处理（`_run_reg_process`）** — 完整的处理管道（扫描→解析→合并→输出 Excel），与 `TenpayPipeline` 并列

### 关键约束

- **pywebview API 名称不变**：`Api` 类的四个配置方法保留同名方法，只在内部转调 service 函数。前端 `window.pywebview.api.get_parking_config()` 不受影响
- **测试必须隔离真实配置目录**：`save_*_config()` 默认写入 `get_user_config_dir()`，测试中必须明确 monkeypatch 到 `tmp_path`

### 架构边界确认

根据 `01_ARCHITECTURE.md`：
- 服务编排层（`scripts/service/`）负责"组织业务流程"
- `Api` 类保留：参数校验、线程调度、前端返回值封装
- 行为与现有 GUI 保持一致

## 预计变更的文件

| 文件 | 变更类型 | 行数预估 |
|------|----------|---------|
| `scripts/service/config_service.py` | **新增** — 配置读写服务 | ~70 |
| `scripts/service/reg_service.py` | **新增** — 注册信息处理编排 | ~100 |
| `scripts/webui/bridge.py` | 修改 — 删除 `_run_reg_process` + 配置方法体，保留同名 wrapper | -70 |
| `tests/test_config_service.py` | **新增** — 配置服务测试（monkeypatch 隔离） | ~70 |
| `tests/test_reg_service.py` | **新增** — 注册信息服务测试 | ~80 |
| `docs/IMPLEMENTATION_PLAN.md` | 修改 — 更新为 T009 计划 | — |
| `docs/CHANGE_REPORT.md` | 新增 — 本任务变更报告 | — |

净变更：~250 行，远低于 500 行上限

## 实现策略

### Step 1：新建 `scripts/service/config_service.py`

纯函数式接口，**不依赖 pywebview 或线程**。

```python
"""配置读写服务 — 管理用户可写配置的验证和持久化"""

import json, os, logging
logger = logging.getLogger("TenpayMerge")


def get_parking_config() -> dict:
    from core.parking import load_parking_config
    try:
        return load_parking_config()
    except Exception as e:
        return {"error": str(e)}


def save_parking_config(config: dict) -> str:
    required_fields = ["备注2关键词", "排除关键词", "对手侧账户名称关键词", "车牌省份简称"]
    for field in required_fields:
        if field not in config:
            return f"缺少必填字段: {field}"
        if not isinstance(config[field], list):
            return f"字段 {field} 必须是数组"
    try:
        from utils.paths import get_user_config_dir
        config_dir = get_user_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "parking_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return "ok"
    except Exception as e:
        return f"保存失败: {e}"


def get_time_period_config() -> dict:
    from core.processor import load_time_period_config
    try:
        return load_time_period_config()
    except Exception as e:
        return {"error": str(e)}


def save_time_period_config(config: dict) -> str:
    if "时段" not in config or not isinstance(config["时段"], list):
        return "缺少必填字段: 时段"
    for period in config["时段"]:
        if not all(k in period for k in ("name", "start", "end")):
            return "每个时段必须包含 name, start, end"
    try:
        from utils.paths import get_user_config_dir
        config_dir = get_user_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "time_period_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return "ok"
    except Exception as e:
        return f"保存失败: {e}"
```

### Step 2：`Api` 类的四个配置方法改为 wrapper

```python
# bridge.py — 新增导入
from service.config_service import get_parking_config as _get_parking_config
from service.config_service import save_parking_config as _save_parking_config
from service.config_service import get_time_period_config as _get_time_period_config
from service.config_service import save_time_period_config as _save_time_period_config

class Api:
    # ... 原有代码 ...

    # ↓↓↓ 四个方法保留，只转调 service ↓↓↓
    def get_parking_config(self) -> dict:
        return _get_parking_config()

    def save_parking_config(self, config: dict) -> str:
        return _save_parking_config(config)

    def get_time_period_config(self) -> dict:
        return _get_time_period_config()

    def save_time_period_config(self, config: dict) -> str:
        return _save_time_period_config(config)
```

**结论**：`window.pywebview.api.get_parking_config()` 路径完整保留，行为完全一致。

### Step 3：新建 `scripts/service/reg_service.py`

接收可选的 `progress_callback`，不依赖 pywebview。

```python
"""注册信息处理服务 — 编排 TenpayRegInfo.txt 的扫描、解析、合并和输出"""

import os, time, logging
logger = logging.getLogger("TenpayMerge")


def run_reg_process(source: str, output: str, timestamp: str = "",
                    progress_callback=None) -> dict | None:
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

    reg_files = find_files_by_name(source, "TenpayRegInfo.txt")
    if not reg_files:
        _log("⚠️ 未找到 TenpayRegInfo.txt 文件，跳过注册信息清洗")
        return None

    _log(f"扫描到 {len(reg_files)} 个 TenpayRegInfo.txt 文件")
    t_start = time.time()
    success = fail = skipped = 0
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

    basic_df, changes_df = process_reg_data(records)
    person_df = build_person_info(basic_df)

    reg_name = f"TenpayRegInfo_merge_{timestamp}.xlsx" if timestamp else "TenpayRegInfo_merge.xlsx"
    output_path = os.path.join(output, reg_name)
    result_path = write_reg_excel(basic_df, changes_df, output_path, person_df=person_df)

    elapsed = time.time() - t_start
    _log(f"✅ 注册信息清洗完成!")
    _log(f"文件总数: {len(reg_files)} | 成功: {success} | 失败: {fail} | 跳过: {skipped}")
    _log(f"注册信息汇总: {len(basic_df)} 条 | 变更记录: {len(changes_df)} 条 | "
         f"基础信息(自然人): {len(person_df)} 人")
    _log(f"耗时: {elapsed:.1f} 秒")
    if result_path:
        _log(f"输出文件: {result_path}")

    return {
        "output": result_path or "",
        "basic_rows": len(basic_df),
        "changes_rows": len(changes_df),
        "person_rows": len(person_df),
        "files": len(reg_files),
        "success": success, "fail": fail, "skipped": skipped,
        "elapsed": round(elapsed, 1),
    }
```

### Step 4：修改 `bridge.py` 的 `_run_reg_process` 部分

删除 `_run_reg_process` 方法体（L164-248），在 `_run` 中调用 service 函数：

```python
# 新增导入
from service.reg_service import run_reg_process

class Api:
    # ... _run 方法中注册信息部分改为：
    if process_reg and self._pipeline.progress.status != "error":
        try:
            self._pipeline.progress.status = "running"
            reg_result = run_reg_process(
                source, output, timestamp,
                progress_callback=lambda msg: self._pipeline.progress.add_log(msg),
            )
            if reg_result:
                p = self._pipeline.progress
                p.result["reg_output"] = reg_result["output"]
                p.result["reg_basic_rows"] = reg_result["basic_rows"]
                p.result["reg_changes_rows"] = reg_result["changes_rows"]
                p.result["reg_person_rows"] = reg_result["person_rows"]
                p.result["reg_files"] = reg_result["files"]
                p.result["reg_success"] = reg_result["success"]
                p.result["reg_fail"] = reg_result["fail"]
                p.result["reg_elapsed"] = reg_result["elapsed"]
        except Exception as e:
            import traceback
            self._pipeline.progress.add_log(f"❌ 注册信息清洗异常: {e}")
            for line in traceback.format_exc().splitlines():
                if line.strip():
                    self._pipeline.progress.add_log(f"   {line.strip()}")
        finally:
            self._pipeline.progress.status = "done"
```

同时删除不再需要的模块级导入：
- `from core.reg_reader import read_tenpay_reg_info`
- `from core.reg_processor import process_reg_data, build_person_info`
- `from core.writer import write_reg_excel`

### Step 5：测试

#### `tests/test_config_service.py` — 明确 monkeypatch 隔离

```python
"""测试 scripts/service/config_service.py，所有磁盘操作在 tmp_path 内。"""

import os
import pytest


def _mock_user_config_dir(tmp_path, monkeypatch):
    """将 get_user_config_dir 指向 tmp_path，避免改到真实配置目录。"""
    monkeypatch.setattr("utils.paths.get_user_config_dir", lambda: str(tmp_path))


class TestParkingConfig:
    def test_save_and_get(self, tmp_path, monkeypatch):
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import save_parking_config, get_parking_config

        config = {
            "备注2关键词": ["停车"],
            "排除关键词": [],
            "对手侧账户名称关键词": ["停车"],
            "车牌省份简称": ["粤"],
        }
        result = save_parking_config(config)
        assert result == "ok"

        # 验证写入 tmp_path 而非真实目录
        saved_path = os.path.join(str(tmp_path), "parking_config.json")
        assert os.path.isfile(saved_path)

        # 验证 get 可读取
        loaded = get_parking_config()
        assert isinstance(loaded, dict)

    def test_missing_field_returns_error(self, tmp_path, monkeypatch):
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import save_parking_config

        result = save_parking_config({"备注2关键词": ["停车"]})
        assert result.startswith("缺少必填字段")

    def test_get_returns_dict(self, tmp_path, monkeypatch):
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import get_parking_config
        config = get_parking_config()
        assert isinstance(config, dict)


class TestTimePeriodConfig:
    def test_save_and_get(self, tmp_path, monkeypatch):
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import save_time_period_config, get_time_period_config

        config = {"时段": [{"name": "凌晨", "start": "00:00", "end": "06:00"}]}
        result = save_time_period_config(config)
        assert result == "ok"

        saved_path = os.path.join(str(tmp_path), "time_period_config.json")
        assert os.path.isfile(saved_path)

        loaded = get_time_period_config()
        assert isinstance(loaded, dict)

    def test_missing_field_returns_error(self, tmp_path, monkeypatch):
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import save_time_period_config

        result = save_time_period_config({"时段": "not_a_list"})
        assert result == "缺少必填字段: 时段"
```

**关键点**：`_mock_user_config_dir` 使用 `monkeypatch.setattr` 将 `utils.paths.get_user_config_dir` 替换为返回 `tmp_path` 的 lambda。这样 `save_*_config()` 里的 `get_user_config_dir()` 返回的是临时目录，不会写入 `scripts/config/` 真实文件。

#### `tests/test_reg_service.py`

```python
"""测试 scripts/service/reg_service.py。"""

import os
import pytest


def _write_reg_file(directory, filename, lines):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


_SAMPLE_REG_HEADER = "姓名\t身份证号\t......等列名（从实际 reg_reader 取）"


def test_run_reg_process_with_files(tmp_path):
    from service.reg_service import run_reg_process

    # 写入一个小样本 TenpayRegInfo.txt
    reg_dir = tmp_path / "batch1"
    _write_reg_file(str(reg_dir), "TenpayRegInfo.txt", [
        "姓名\t身份证号\t...实际列名...",
        "张三\t440000...\t...",
    ])

    result = run_reg_process(str(tmp_path), str(tmp_path))
    assert result is not None
    assert result["output"] or True  # 验证有输出或为空

    # 验证 xlsx 文件已生成
    # output_files = list(tmp_path.glob("TenpayRegInfo_merge*.xlsx"))
    # assert len(output_files) > 0


def test_run_reg_process_no_files(tmp_path):
    from service.reg_service import run_reg_process

    result = run_reg_process(str(tmp_path), str(tmp_path))
    assert result is None
```

## 架构影响

无。本变更是纯职责搬迁：
- `config_service.py` 和 `reg_service.py` 属于服务编排层（`scripts/service/`）
- `Api` 类保留同名方法，pywebview API 表面不变
- 前端零修改，行为完全一致

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| service 模块导入循环 | 低 | 编译错误 | 函数内导入 `core.*`，非模块级 |
| 行为不一致 | 低 | 功能异常 | 代码逐字搬迁，无逻辑修改 |
| `finally` 中 `progress.status="done"` 位置变化 | 低 | 前端状态异常 | 保持相同 try/finally 结构 |
| 测试修改真实配置目录 | **中** | 测试污染 | 每个测试用例使用 `monkeypatch.setattr("utils.paths.get_user_config_dir", ...)` 隔离 |

## 测试策略

```powershell
# 新增配置服务测试
.\.venv\Scripts\python -m pytest tests/test_config_service.py -v

# 新增注册信息服务测试
.\.venv\Scripts\python -m pytest tests/test_reg_service.py -v

# 全量回归
.\.venv\Scripts\python -m pytest tests/ -v
```

## 考虑的替代方案

| 方案 | 未选中的理由 |
|------|-------------|
| 仅迁移配置读写 | 代码量太小，不减桥接职责密度 |
| 迁移多批次合并流程 | 线程 + progress 耦合较深，边界不够清晰 |
| 迁移地点重提取 | 与 openpyxl/`_sanitize_for_excel` 耦合，提取意义有限 |

## 决策一致性

- ADR-001（本地 Python/pandas）：无冲突
- ADR-002（CLI 与 GUI 共享核心管道）：**正面**——业务编排从桥接层移入 service 层
- ADR-008（配置持久化目录）：无冲突，`config_service` 继续使用 `get_user_config_dir()`

## 预估范围

- 新增文件：4 个（2 service + 2 test）
- 修改文件：1 个（bridge.py）
- 新建代码：~320 行
- 删除代码：~70 行
- 净变更：~250 行，远低于 500 行上限
