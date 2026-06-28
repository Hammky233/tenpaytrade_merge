# 实现计划 — T007

## 任务 ID

T007

## 目标

区分内置默认配置和用户可写配置，避免 PyInstaller onefile 环境下写入 `_MEIPASS` 临时目录导致重启后配置丢失。

## 理解分析

**现状：**

所有配置（parking_config.json、time_period_config.json、special_filter_config.json、mahjong_config.json、location_config.json）统一通过 `scripts/utils/paths.py` 的 `get_config_dir()` 获取路径：

- 开发环境：`get_config_dir()` → `<项目根>/scripts/config/`（基于 `__file__` 推算）
- PyInstaller onefile 打包：`get_config_dir()` → `sys._MEIPASS/scripts/config/`（临时解压目录）

读取场景（全部正常）：五个 `load_*_config()` 函数均经由 `config_loader.load_json_config()` → `get_config_dir()`，读取内置默认配置。

写入场景（打包后异常）：`bridge.py` 的 `save_parking_config()` 和 `save_time_period_config()` 直接 `open(config_path, "w")` 写入 `get_config_dir()`。在打包环境下，该路径是 `_MEIPASS` 临时目录，重启后操作系统回收，配置丢失。

**影响范围：**

| 文件 | 角色 | 需修改 |
|------|------|--------|
| `scripts/utils/paths.py` | 路径工具 | 新增 `get_user_config_dir()` |
| `scripts/utils/config_loader.py` | 配置加载器 | 修改读取策略（用户配置优先） |
| `scripts/webui/bridge.py` | GUI API | 修改保存目标为用户配置目录 |
| `scripts/config/` 目录 | 默认配置 | 不变 |

## 预计变更的文件

| 文件 | 变更类型 |
|------|----------|
| `scripts/utils/paths.py` | 修改 — 新增 `get_user_config_dir()` |
| `scripts/utils/config_loader.py` | 修改 — 双层读取策略 |
| `scripts/webui/bridge.py` | 修改 — 保存写入改为用户配置目录 |
| `docs/02_DECISIONS.md` | 修改 — 新增 ADR-008 |
| `docs/IMPLEMENTATION_PLAN.md` | 新增 — 本文件 |

## 实现策略

### Step 1：paths.py — 新增 `get_user_config_dir()`

新增函数，返回用户可写的配置持久化目录：

- 开发环境：与 `get_config_dir()` 返回相同路径（`scripts/config/`），行为完全兼容
- PyInstaller 打包：`%APPDATA%/tenpaytrade/config/`

选择 `%APPDATA%/tenpaytrade/config/` 的理由：
- Windows 标准应用数据目录，用户有写权限
- 卸载时随 AppData 清理（如用户选择清除）
- 与 `_MEIPASS` 完全隔离，不受临时目录生命周期影响

### Step 2：config_loader.py — 双层读取策略

修改 `load_json_config()` 逻辑链：

```
用户配置目录 → 找到 → 返回用户配置
用户配置目录 → 未找到 → 内置配置目录 → 找到 → 返回默认配置
用户配置目录 → 未找到 → 内置配置目录 → 未找到 → 返回 defaults 参数
```

开发环境下用户配置目录 == 内置配置目录，所以第一步直接命中，行为不变。

读取时若用户配置目录不存在（打包后首次运行），不创建目录、不写入，静默降级到内置配置。目录仅在实际保存时创建。

### Step 3：bridge.py — 保存写入改为用户配置目录

`save_parking_config()` 和 `save_time_period_config()` 中：
- 导入目标从 `get_config_dir` 改为 `get_user_config_dir`
- 保存前 `os.makedirs(os.path.dirname(config_path), exist_ok=True)` 确保目录存在

### Step 4：docs/02_DECISIONS.md — 新增 ADR-008

记录配置持久化目录的技术决策。

## 架构影响

- 不改变配置 JSON 的业务字段含义（约束条件）
- 不引入数据库（约束条件）
- 不改变开发环境行为（用户配置目录 === 内置配置目录）
- 新增 `get_user_config_dir()` 函数，现有 `get_config_dir()` 保持不变

架构边界检查：本变更符合 `01_ARCHITECTURE.md` 第 7 节要求——"打包环境下配置的读取和写入策略必须明确区分内置默认配置与用户可写配置"。

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| APPDATA 环境变量不存在 | 低 | 写入失败 | fallback 到 `os.path.expanduser('~')` |
| 用户配置目录未创建 | 低 | 写入失败 | 保存前 `makedirs(exist_ok=True)` |
| 开发环境用户与内置不一致 | 无 | — | 开发环境返回同一路径 |
| 现有读取行为变化 | 无 | — | 开发环境首次命中不变，打包环境新增 fallback |

## 测试策略

1. **单元测试**：新增 `tests/test_paths.py` 验证 `get_user_config_dir()` 在开发环境返回与 `get_config_dir()` 相同
2. **回归**：运行现有全量测试套件确保无破坏

```powershell
# 新增路径测试
.\.venv\Scripts\python -m pytest tests/test_paths.py -v

# 全量回归
.\.venv\Scripts\python -m pytest tests/ -v
```

## 考虑的替代方案

| 方案 | 未选中的理由 |
|------|-------------|
| 保存在 exe 同目录 | onefile 模式 exe 可能在 Program Files 等只读位置 |
| 保存在 `%LOCALAPPDATA%` | 适合缓存/临时数据，Roaming 更适合配置漫游 |
| 保存在注册表 | 与项目纯文件架构不符，增加复杂度 |
| 环境变量覆盖 | 增加用户认知负担，且无明确需求 |

## 决策一致性

- ADR-001（本地 Python/pandas）：无冲突
- ADR-005（基础功能不依赖网络）：无冲突
- ADR-007（地点 AI 配置 JSON 管理）：新决策与其一致，均使用 JSON 文件 + 路径工具管理

新增 ADR-008 记录配置持久化目录选择。

## 预估范围

- 修改文件：3 个 Python 文件 + 1 个文档
- 新增代码：约 25 行（含注释和空行）
- 修改代码：约 10 行（替换导入和调用）
- 总变更量：远低于 500 行和 10 个文件的升级规则
