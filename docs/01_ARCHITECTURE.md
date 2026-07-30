# 项目架构说明

本文档是四文档唯一事实来源体系的一部分（另见 `docs/00_REQUIREMENTS.md`、`docs/02_DECISIONS.md`、`docs/03_TASKS.md`），描述当前系统架构边界、模块职责和实现约束。实现代理在制定计划和修改代码前，必须先确认变更是否仍处于本文档定义的架构内。

## 1. 架构目标

本项目是一个本地运行的财付通交易流水清洗、合并和分析工具。架构目标是：

- 以本地文件系统为输入输出边界。
- 通过 Python/pandas 完成核心数据处理。
- 通过 Excel 工作簿交付清洗和分析结果。
- 通过 CLI 和桌面 GUI 复用同一套核心处理逻辑。
- 在国内网络环境下保持基础功能可用，GUI 前端不依赖 CDN。

## 2. 总体分层

系统按以下层次组织：

- 入口层：`scripts/app.py`、`scripts/app_merge.py`、`scripts/app_reg.py`、`scripts/gui_app.py`
- GUI 桥接层：`scripts/webui/bridge.py`
- 服务编排层：`scripts/service/pipeline.py`
- 核心领域层：`scripts/core/`
- 工具层：`scripts/utils/`
- 配置层：`scripts/config/`
- 静态前端：`scripts/webui/static/`

入口层只负责参数解析、日志初始化和调用下层服务。核心业务规则应放在 `scripts/core/` 或 `scripts/service/` 中，不应散落在入口脚本中。

## 3. 入口层职责

### 3.1 单批次交易流水

`scripts/app.py` 调用 `TenpayPipeline` 完成目录扫描、读取、清洗、合并、去重、后处理分析和 Excel 输出。

### 3.2 多批次合并

`scripts/app_merge.py` 读取历史 Excel 输出，复用 `merge_dataframes()`、`deduplicate()`、`post_merge_analysis()` 和 `write_excel()`。

### 3.3 注册信息

`scripts/app_reg.py` 读取 `TenpayRegInfo.txt`，复用注册信息读取、处理和输出模块。

### 3.4 桌面 GUI

`scripts/gui_app.py` 只负责启动 pywebview 窗口。前端通过 `scripts/webui/bridge.py` 调用 Python API。

## 4. 服务编排层职责

`scripts/service/pipeline.py` 是交易流水处理主编排层，负责组织以下流程：

1. 查找 `TenpayTrades.txt`
2. 读取文本
3. 清洗单文件 DataFrame
4. 合并多个 DataFrame
5. 去重
6. 停车缴费识别
7. 可选 AI 地点识别
8. 特殊交易筛选
9. 疑似麻友识别
10. 群红包识别
11. Excel 输出

`post_merge_analysis()` 是单批次、CLI 合并、GUI 合并的共享后处理入口。新增后处理分析功能时，应优先接入该函数，避免不同入口行为分叉。

## 5. 核心领域层职责

`scripts/core/` 中各模块职责如下：

- `reader.py`：读取 `TenpayTrades.txt`，处理编码、空文件、重复表头和列数异常。
- `processor.py`：清洗交易流水字段，包含列名清洗、重复列合并、金额转换、时间拆分、进出账拆分、时段分类和日期分类。
- `merger.py`：合并 DataFrame 并执行联合主键去重。
- `parking.py`：停车缴费识别、车牌提取和复核标记。
- `special_filter.py`：特殊日期、金额、备注和对手侧账户名称的可配置特殊交易筛选及旧配置兼容。
- `mahjong.py`：疑似麻友识别，基于独立分析时段和固定圈子共同出现规则输出明细、对手方统计、圈子统计。
- `group_red_packet.py`：群红包识别。
- `location.py`：停车地点 AI 提取。
- `reg_reader.py`：读取注册信息。
- `reg_processor.py`：合并和转换注册信息。
- `writer.py`：Excel 输出、格式化、隐藏列、固定列宽和注册信息输出。

核心领域层不得依赖 GUI。核心模块可以依赖 `utils` 和配置文件，但不应依赖 `webui`。

## 6. 工具层职责

`scripts/utils/` 提供跨模块辅助能力：

- `columns.py`：自适应列名识别。
- `clean_text.py`、`text_utils.py`：文本清理和行字段标准化。
- `encoding.py`：编码检测读取。
- `time_utils.py`：时间字符串解析。
- `config_loader.py`：JSON 配置加载。
- `paths.py`：开发环境与 PyInstaller 环境路径解析。
- `logger.py`：日志初始化。

工具层应保持无业务状态，不应引入交易分析规则。

## 7. 配置边界

业务配置位于 `scripts/config/`：

- `parking_config.json`
- `time_period_config.json`
- `special_filter_config.json`
- `mahjong_config.json`

配置用于调整规则参数，不应用于隐藏改变架构行为。打包环境下配置的读取和写入策略必须明确区分内置默认配置与用户可写配置。

疑似麻友分析时段是 `mahjong_config.json` 的独立业务配置，不复用 `time_period_config.json` 的“时段”分类结果。

## 8. 输出边界

系统输出为本地 Excel 文件。交易流水输出主表为“财付通交易汇总”，附加分析表按命中情况生成。注册信息输出包含“注册信息汇总”“变更记录”“基础信息”。

Excel 格式化属于 `writer.py` 职责。其他模块不应直接操作输出格式，除非该行为被记录为架构决策。

## 9. 外部服务边界

基础清洗、合并、识别和 Excel 输出不依赖网络。

停车地点 AI 识别是可选功能，调用 DeepSeek API。该功能失败时不得影响主流程基础输出。API Key 不应持久化保存。

## 10. 变更约束

实现代理可以在现有架构内进行局部修复、测试补充和小规模重构。以下变更需要先更新 `docs/02_DECISIONS.md` 并获得审查：

- 引入新的 GUI 框架。
- 引入数据库或持久化服务。
- 改变 CLI/GUI 与核心处理层的通信方式。
- 改变 Excel 作为主要交付物的策略。
- 大规模拆分或重写核心管道。
- 新增必须联网才能运行的核心功能。
