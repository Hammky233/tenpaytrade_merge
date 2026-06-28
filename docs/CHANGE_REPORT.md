# 变更报告 — T007

## 变更的文件

| 文件 | 变更类型 |
|------|----------|
| `scripts/utils/paths.py` | 修改 — 新增 `get_user_config_dir()` |
| `scripts/utils/config_loader.py` | 修改 — 双层配置读取策略（用户优先 → 内置兜底） |
| `scripts/webui/bridge.py` | 修改 — `save_parking_config` / `save_time_period_config` 写入用户配置目录 |
| `tests/conftest.py` | 修改 — 新增 `temp_config_dirs` fixture |
| `tests/test_paths.py` | 新增 — 路径工具测试（4 用例） |
| `tests/test_config_loader.py` | 新增 — 双层配置加载测试（4 用例） |
| `docs/02_DECISIONS.md` | 修改 — 新增 ADR-008 |
| `docs/CHANGE_REPORT.md` | 新增 — 本报告 |

## 变更摘要

将打包环境下 GUI 配置持久化路径从 `_MEIPASS/scripts/config/`（临时目录，重启丢失）改为 `%APPDATA%/tenpaytrade/config/`（稳定持久目录），并实现用户配置优先、内置默认配置兜底的双层读取策略。

### 具体修改

**paths.py — 新增 `get_user_config_dir()`：**
- 开发环境：返回与 `get_config_dir()` 相同的 `scripts/config/`
- PyInstaller 打包：返回 `%APPDATA%/tenpaytrade/config/`
- APPDATA 不存在时 fallback 到 `os.path.expanduser('~')`

**config_loader.py — 双层读取策略：**
- 读取顺序：用户配置目录 → 内置默认配置目录 → `defaults` 参数
- 用户配置存在时优先返回，内置配置作为兜底
- 用户配置 JSON 损坏时自动降级到内置配置
- 开发环境下用户目录 == 内置目录，行为完全不变

**bridge.py — 保存路径修正：**
- `save_parking_config()`：写入 `get_user_config_dir()`，保存前 `makedirs(exist_ok=True)`
- `save_time_period_config()`：同上

**ADR-008 — 新增技术决策：**
- 记录配置持久化目录选择为 `%APPDATA%/tenpaytrade/config/`
- 理由：Windows 标准应用数据目录、与 `_MEIPASS` 隔离、向后兼容

## 添加的测试

| 测试文件 | 用例 | 覆盖场景 |
|----------|------|----------|
| `test_paths.py` | 4 | 开发环境路径正确性、用户与内置目录一致、打包环境 APPDATA 路径、无 APPDATA fallback |
| `test_config_loader.py` | 4 | 用户优先、内置兜底、全缺失返回 defaults、用户配置损坏降级 |

## 已执行的测试

```
tests/ 全量回归：68 passed in 1.37s
  新增 8 测试全部通过
  现有 60 测试无回归
```

## 已知风险

无。开发环境行为完全向后兼容（用户目录 == 内置目录），打包环境新增路径 fallback 机制。

## 经验教训

1. **配置持久化是桌面应用的隐式需求**：PyInstaller onefile 打包下 `_MEIPASS` 不可写，初期未考虑写入场景导致了配置丢失 bug。
2. **双层读取比"安装时复制"更简单**：不需要首次运行的配置迁移逻辑，用户配置优先 + 内置兜底自然覆盖了所有场景。
3. **`%APPDATA%` 是 Windows 桌面应用的合理持久化位置**：无需自行设计目录结构，遵循 OS 惯例即可。
