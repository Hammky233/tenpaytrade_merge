# 技术决策记录

本文档是四文档唯一事实来源体系的一部分（另见 `docs/00_REQUIREMENTS.md`、`docs/01_ARCHITECTURE.md`、`docs/03_TASKS.md`），记录架构层面的决策。新增或改变架构行为前，必须先更新本文档。

## ADR-001 使用本地 Python/pandas 作为核心处理引擎

背景：

项目需要批量处理财付通文本流水，执行清洗、合并、分类和统计分析，并输出 Excel。

考虑的选项：

- 使用 Python/pandas 本地处理。
- 使用数据库导入后通过 SQL 处理。
- 使用前端 JavaScript 直接处理文件。

选定的方案：

使用 Python/pandas 作为核心处理引擎。

理由：

- pandas 适合表格数据清洗和向量化计算。
- 项目当前依赖和代码结构已经围绕 pandas 建立。
- 本地处理不要求部署数据库，符合单机工具定位。

后果：

- 大数据量性能主要受 pandas 内存占用影响。
- 复杂规则应优先用向量化实现，避免逐行处理。

## ADR-002 CLI 与 GUI 共享核心处理管道

背景：

项目同时提供 CLI 和桌面 GUI。两种入口都需要执行相同清洗和分析规则。

考虑的选项：

- CLI 和 GUI 各自实现处理流程。
- GUI 仅调用 CLI 命令。
- CLI 和 GUI 共享 Python 服务层和核心模块。

选定的方案：

CLI 和 GUI 共享 `scripts/service/pipeline.py`、`scripts/core/` 和 `scripts/utils/`。

理由：

- 避免不同入口行为不一致。
- 便于测试核心逻辑。
- GUI 只承担交互和线程调度职责。

后果：

- 新增业务后处理应接入共享函数 `post_merge_analysis()`。
- 不应在前端或 bridge 中重复实现核心业务规则。

## ADR-003 使用 Excel 作为主要交付格式

背景：

目标用户需要可直接查看、筛选和人工复核的交付物。

考虑的选项：

- 输出 Excel。
- 输出 CSV。
- 输出数据库。

选定的方案：

使用 Excel 作为主要交付格式，CSV 仅作为异常 fallback。

理由：

- Excel 支持多工作表、冻结表头、隐藏列、列宽、标黄复核。
- 适合案件分析和人工复核场景。

后果：

- 输出格式化集中在 `scripts/core/writer.py`。
- 修改已有 Excel 时必须注意保留工作簿格式。

## ADR-004 使用自适应列名识别而非固定列序号

背景：

财付通返回字段顺序和名称可能变化。

考虑的选项：

- 固定列序号。
- 固定完整列名。
- 关键词组合识别列。

选定的方案：

通过 `utils.columns.find_column()` 和 `find_columns_containing()` 进行关键词组合识别。

理由：

- 对字段顺序变化更稳健。
- 对列名轻微变化有一定容错。

后果：

- 新增规则应优先使用列识别工具。
- 匹配关键词必须谨慎，避免误匹配。

## ADR-005 基础功能不依赖网络，AI 地点识别作为可选增强

背景：

停车地点识别可能需要大模型辅助，但项目运行环境在国内网络环境下，外部服务可用性不可保证。

考虑的选项：

- 所有停车地点识别都依赖 API。
- 完全不使用外部 API。
- 基础功能离线运行，地点识别可选联网。

选定的方案：

基础清洗和规则识别离线运行，AI 地点识别作为可选增强。

理由：

- 保证核心功能稳定。
- API Key 不持久化，降低敏感信息风险。

后果：

- API 失败不得中断主清洗结果输出。
- 网络调用错误需要向用户提供可理解的信息。

## ADR-006 GUI 前端本地预编译构建，不依赖 CDN

背景：

项目运行环境可能无法稳定访问外部 CDN。此前使用 Babel Standalone 在运行时编译 JSX。
T010 评估后决定改为 esbuild 构建时预编译，以消除 3 MB Babel 运行时的体积和启动成本。

考虑的选项：

- 从 CDN 加载 React/Babel。
- 将前端依赖放入本地静态目录，运行时 Babel 编译。
- **选定的方案**：将前端依赖放入本地静态目录，esbuild 构建时预编译 JSX。

选定的方案：

使用 esbuild 构建时预编译 JSX，`app.jsx`（JSX 源码）→ `static/app.js`（纯 JS）。
构建产物提交到仓库，确保检出即运行。

理由：

- 离线可用（所有资源仍在本地 `static/` 内）。
- 运行时移除 3 MB Babel Standalone 开销，缩小打包体积 ~3 MB。
- 构建耗时 < 5ms，几乎不影响开发流程。
- esbuild 是 Rust 编写的极速构建工具，无复杂配置。

后果：

- 引入 Node/esbuild 作为开发时构建工具（仅 devDependency，不进入打包）。
- 运行时不依赖 Node/npm，浏览器直接加载 `static/app.js`。
- PyInstaller 只包含构建产物（`static/` 内文件），不包含源码或构建工具。
- 修改前端源码（`scripts/webui/app.jsx`）后需运行 `npm run build` 生成 `static/app.js`。
- 可使用 `npm run watch` 在开发时自动重建。
- 开发环境和 CI 需要 Node.js 来构建前端（已有 `package.json` 和 `node_modules/`）。

## ADR-007 地点 AI 识别配置使用 JSON 文件管理

背景：

停车地点 AI 识别的模型名和运行参数在 `scripts/core/location.py` 中硬编码。DeepSeek 模型名随版本迭代变化（如 deepseek-chat、deepseek-reasoner），硬编码导致用户需修改代码才能更换模型。其他业务模块（parking、special_filter、mahjong）均已使用 `scripts/config/` 下的 JSON 文件管理参数。

考虑的选项：

- 维持硬编码常量。
- 使用环境变量配置。
- 新增 JSON 配置文件管理。

选定的方案：

新增 `scripts/config/location_config.json`，采用与其他业务模块一致的 JSON 文件管理模型名、并发参数和超时时间。

配置加载沿用 `utils.config_loader.load_json_config()`，文件缺失时使用 `load_location_config()` 中提供的硬编码默认值。

理由：

- 与项目现有配置惯例一致（所有业务模块统一用 JSON 文件）。
- 用户只需编辑 JSON 即可修改模型名，无需接触代码。
- `load_json_config` 内置文件缺失降级，打包环境兼容。
- 通过 PyInstaller `--collect-data` 可自然包含在打包产物中。

后果：

- `API_URL` 仍为硬编码（URL 变更场景远少于模型名，且纳入配置会增加敏感信息面）。
- 用户误修改配置可能导致模型调用失败，但错误信息会被友好提示覆盖。
- 新增配置文件需要打包说明同步更新。

## ADR-008 配置持久化目录使用 %APPDATA%/tenpaytrade

背景：

PyInstaller onefile 打包后，`sys._MEIPASS` 是指向临时解压目录。`get_config_dir()` 返回 `_MEIPASS/scripts/config/`，写入该目录的配置在重启后丢失。用户通过 GUI 修改的停车识别或时段分类配置无法持久化保存。

考虑的选项：

- 使用 `%APPDATA%/tenpaytrade/config/` 作为用户可写配置目录。
- 保存在 exe 同目录（onefile 模式 exe 可能在只读位置）。
- 保存在 `%LOCALAPPDATA%`（更适合缓存而非配置）。
- 使用注册表（与项目纯文件架构不符）。

选定的方案：

使用 `%APPDATA%/tenpaytrade/config/` 作为用户可写配置目录，`scripts/config/` 仅作为内置默认配置目录。

理由：

- Windows 标准应用数据目录，用户始终有写权限。
- 与 `_MEIPASS` 临时目录完全隔离，不受重启影响。
- 开发环境下 `get_user_config_dir()` 返回与 `get_config_dir()` 相同的路径，行为完全向后兼容。
- 读取策略：用户配置优先 → 内置默认配置兜底。

后果：

- 打包后首次运行时 `%APPDATA%/tenpaytrade/config/` 不存在，`load_json_config()` 静默降级到 `_MEIPASS/scripts/config/` 内置配置。
- 用户通过 GUI 保存配置时自动创建该目录。
- 所有配置 JSON 的业务字段含义不变。
