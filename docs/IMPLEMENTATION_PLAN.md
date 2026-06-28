# 实现计划 — T006（修正版）

## 任务 ID

T006

## 目标

同步 README 版本号与 `scripts/version.py` 保持一致，补充 CHANGELOG 缺失的发布记录，增加发布检查说明避免后续版本漂移。

## 理解分析

### 版本不一致现状

| 位置 | 当前值 | 正确值 | 差异分析 |
|------|--------|--------|----------|
| `scripts/version.py` | `4.3` | `4.3` ✅ | 唯一事实来源，不动 |
| `README.md` 标题 | `v4.0` | `v4.3` ❌ | 落后三期；`version.py` 注释要求“全局搜索 v4.x 更新静态文件” |
| `scripts/webui/static/index.html` 标题 | `v4.2` | `v4.3` ❌ | 落后一期，同上 |
| `CHANGELOG.md` | 只到 v4.1 | 缺 v4.2、v4.3 ❌ | v4.1（2026-06-11）之后无记录 |

### README 内容落后现状

- 功能列表未列注册信息提取合并、群红包识别、AI 地点提取
- 架构图缺失 `location.py`、`mahjong.py`、`group_red_packet.py`、`reg_reader.py`、`reg_processor.py`、`encoding.py`、`text_utils.py`、`time_utils.py`
- 配置表缺失 `location_config.json`、`mahjong_config.json`

### 约束边界

T006 约束为“不修改运行时代码”。`index.html` 的 `<title>` 标签属于**静态显示文本**——它由 GUI 窗口读取并显示标题文本，运行时不被任何逻辑依赖。`version.py` 注释明确指示“全局搜索 v4.x 更新静态文件中的显示文本”，本任务中的 `<title>` 修改正是该指令的执行，不属于运行时代码修改。

## 发布记录核验（依据 git 提交历史）

以下为本次 CHANGELOG 补充内容的核验过程：

### v4.2 发布核验（2026-06-14）

依据以下 3 个提交：

| 提交 | 日期 | 文件变更概要 |
|------|------|-------------|
| `a05d49f` | 2026-06-14 17:34 | 新建 `core/group_red_packet.py`（群红包识别）+ 集成到 pipeline/bridge/writer |
| `118c004` | 2026-06-14 21:58 | 修改 `core/merger.py`：8 列联合主键替代自适应降级策略 |
| `690940f` | 2026-06-14 22:05 | 版本号 4.1→4.2、制作人展示、群红包统计按次数排序 |

核验方法：`git show --stat <hash>` 确认变更文件列表，`git diff <hash>~1..<hash>` 核对变更内容。

### v4.3 发布核验（2026-06-17）

| 提交 | 日期 | 文件变更概要 |
|------|------|-------------|
| `15087b1` | 2026-06-17 16:50 | 新建 `core/location.py`（AI 地点提取）+ pipeline/bridge/frontend 集成 + version 4.2→4.3 |

核验方法同上。

### 不纳入本次 CHANGELOG 的内容

- **T004 HTTP 错误分类处理**（location.py 修改）：虽已实施，但尚未发版（无对应版本号提交）
- **mahjong.py / encoding.py / text_utils.py / time_utils.py**：仍未提交（git untracked），尚未纳入任何发布

以上内容将在后续发版时写入 CHANGELOG。

## 预计变更的文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `README.md` | 修改 | 标题版本号 + 功能列表追补 + 架构树补全 + 配置表补全 + 发布检查说明 |
| `CHANGELOG.md` | 修改 | 插入 v4.2、v4.3 条目（内容经 git 提交核验） |
| `scripts/webui/static/index.html` | 修改 | 标题 `v4.2`→`v4.3`（静态显示文本同步） |
| `docs/03_TASKS.md` | 修改 | T006 状态更新 |
| `docs/CHANGE_REPORT.md` | 新增 | 本任务变更报告 |

## 实现策略

### Step 1：版本号修复（静态显示文本）

- `README.md` 第 1 行：`v4.0` → `v4.3`
- `scripts/webui/static/index.html` 第 6 行：`v4.2` → `v4.3`

### Step 2：CHANGELOG 补充

在 `[4.1]` 条目之上插入 `[4.3]` 和 `[4.2]` 条目：

**v4.3 (2026-06-17)**
- 新增：停车缴费地点识别（AI）— 调用 DeepSeek API 从备注提取停车场/商场名称
  - 7 种常见备注格式 × 30+ few-shot 示例
  - 去重后分块并发（≤100 条/块，8 线程）
  - 已有非"无"地点值保留不覆盖（保护人工修正）
  - 可选功能，API Key 通过 GUI 输入/内存存储，失败不影响主流程
- 新增：`scripts/core/location.py` — DeepSeek 地点提取模块
- 新增：GUI 地点识别复选框 + API Key 输入面板 + 事后重新提取
- 变更：版本号 4.2 → 4.3
- 依赖：仅 `urllib` 标准库，零新增外部依赖

**v4.2 (2026-06-14)**
- 新增：群红包识别功能 — 同日同时多人微信红包检测 + 对手方统计
  - 新建 `core/group_red_packet.py`
  - 输出「群红包记录」和「群红包-统计」两个 Excel sheet
- 修正：去重逻辑 — 8 列联合主键（含对手方 ID）替代自适应降级策略
  - 修复群红包场景误删（多条仅对手方/金额不同者被删剩 1 条）
- 变更：群红包统计排序由金额倒序改为次数倒序
- 变更：CLI/GUI/前端全路径展示制作人信息
- 变更：版本号 4.1 → 4.2

### Step 3：README 内容同步

**功能列表追补**（保持现有列表格式，追加于末尾）：
- 群红包识别
- 停车缴费地点 AI 提取
- 注册信息提取合并

**架构树补全**（`scripts/core/` 组补全）：
```
├── group_red_packet.py    # 群红包识别
├── location.py             # 停车地点 AI 提取
├── mahjong.py              # 疑似麻友识别
├── reg_reader.py           # 注册信息读取
└── reg_processor.py        # 注册信息处理
```

`scripts/utils/` 组补全：
```
├── encoding.py             # 编码检测读取
├── text_utils.py           # 文本工具
└── time_utils.py           # 时间工具
```

**配置表补全**：
| `location_config.json` | 地点识别 AI 参数（模型名/并发数/超时） |
| `mahjong_config.json`  | 麻友识别参数 |

### Step 4：增加发布检查说明

在 `CHANGELOG.md` 顶部（格式参考区块下方）增加发布检查 checklist：

```markdown
## 发布检查

发版前请确认：

1. 更新 `scripts/version.py` 中的 `VERSION` 为新版本号
2. 全局搜索 `v\d+\.\d+`，更新所有静态显示文本中的版本号
3. 为本版本新增 `CHANGELOG.md` 条目，记录新增/变更/修复
4. 运行版本一致性检查（见下方命令）
5. 确认 `git diff --check` 无空白错误
```

## 架构影响

无。仅文档和静态显示文本变更。

## 风险评估

无风险。不改运行时代码，不改功能行为。

## 测试策略

### 版本一致性检查

实现完成后，在 `tests/` 目录外执行以下一致性检查：

```powershell
# 1. 从 version.py 提取当前版本号
$v = (Select-String -Path scripts/version.py -Pattern 'VERSION = "(\d+\.\d+)"').Matches.Groups[1].Value

# 2. README 标题含该版本
Select-String -Path README.md -Pattern "v$v" -Quiet

# 3. index.html 标题含该版本
Select-String -Path scripts/webui/static/index.html -Pattern "v$v" -Quiet

# 4. CHANGELOG 有该版本条目
Select-String -Path CHANGELOG.md -Pattern "\[$v\]" -Quiet

# 5. git diff --check 无空白问题
git diff --check
```

所有检查输出为 `True` 且 `git diff --check` 无错误即通过。

## 考虑的替代方案

- 将 README 版本号改为从 version.py 动态生成：需要构建步骤，不符合项目无构建步骤的惯例

## 决策一致性

`scripts/version.py` 的集中管理机制于 v4.1 引入（见 `CHANGELOG.md` `[4.1]`-变更-“集中版本号管理”）。该变更记录的描述是“`scripts/version.py` 统一定义，Python 入口动态读取，前端通过 bridge API 获取”，并在 `version.py` 注释中要求“全局搜索 v4.x 更新静态文件中的显示文本”。本任务是对该设计意图的执行：同步所有静态显示文本。

## 预估范围

变更 5 个文件，预计新增/修改约 80 行。零风险。
