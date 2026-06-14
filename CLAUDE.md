# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

批量清洗财付通（Tenpay）交易流水数据。从目录树中读取 `TenpayTrades.txt`（UTF-8 + Tab 分隔），清洗转换后合并输出为一个 Excel 文件，支持多批次合并去重。

此外，支持从目录树中遍历 `TenpayRegInfo.txt`（注册信息）提取账号状态、身份变更历史并合并输出。

## 常用命令

```powershell
# CLI 单批次清洗（交易流水）
python scripts/app.py -s <数据源目录> -o <输出目录> [-n 文件名]

# CLI 多批次合并（将多次清洗结果合并去重）
python scripts/app_merge.py -i batch1.xlsx batch2.xlsx -o merged.xlsx

# CLI 注册信息提取合并
python scripts/app_reg.py -s <数据源目录> -o <输出目录> [-n 文件名]

# GUI（pywebview + React）
python scripts/gui_app.py
```

示例：
```powershell
python scripts/app.py -s src_ref/0062_L-1780366225387 -o output
python scripts/app_merge.py -i output/batch_0605.xlsx output/batch_0607.xlsx -o output/merged.xlsx
python scripts/app_reg.py -s src_ref/财付通20260421 -o output
```

### 打包命令

```powershell
# Windows exe（需在项目根目录运行）
pyinstaller --onefile --name tenpaytrade-gui --paths scripts `
  --add-data "scripts/config;scripts/config" `
  --add-data "scripts/utils;scripts/utils" `
  --add-data "scripts/webui/static;scripts/webui/static" `
  --hidden-import=utils.paths `
  --hidden-import=webview.platforms.edgechromium `
  --hidden-import=tkinter scripts/gui_app.py

# 清理中间产物
Remove-Item -Recurse -Force build; Remove-Item -Force *.spec
```

```bash
# Linux（Docker 本地构建）
bash linux_build/build.sh
# 或直接用 PowerShell：
docker run --rm -v "C:\CCProject\tenpaytrade_merge:/project" tenpaytrade-builder bash /project/linux_build/_build_inside.sh
```

## 架构

```
scripts/
├── app.py / app_merge.py       # CLI 入口（单批次交易 / 多批次合并）
├── app_reg.py                  # CLI 入口（注册信息提取合并）
├── gui_app.py                  # pywebview GUI 入口
├── version.py                  # 单一版本号来源（VERSION = "4.1"），Python/前端/打包共享
├── core/
│   ├── reader.py               # txt 读取（交易流水），自动编码检测，空文件跳过
│   ├── reg_reader.py           # txt 读取（注册信息），两区域格式 + 银行卡扩展行 + 账号不存在
│   ├── processor.py            # 清洗流水线：列名清洗→合并重复列→分转元→时间拆分→进账/出账→时段分类→日期分类
│   ├── reg_processor.py        # 注册信息合并：主记录去重 + 变更记录分类（身份变更/注销）
│   ├── merger.py               # 多 DataFrame 合并 + (交易单号+大单号)联合去重
│   ├── parking.py              # 停车缴费识别 + 车牌提取
│   ├── special_filter.py       # 特殊交易筛选（情感数字/特殊日期/特殊备注）
│   ├── mahjong.py              # 疑似麻友识别（晚间转账 + 自然人 + 跨日重复对手方）
│   ├── group_red_packet.py      # 群红包识别（同日同时多人收款 + 对手方统计）
│   └── writer.py               # Excel 输出 + 列宽自适应（支持停车缴费、特殊交易、疑似麻友、群红包、注册信息多 sheet）
├── config/
│   ├── parking_config.json       # 停车识别配置（关键词、排除词、车牌省份简称）
│   ├── time_period_config.json   # 时段分类配置（时段名称、起止时间）
│   └── special_filter_config.json # 特殊交易筛选配置（金额模式、备注关键词、2/14开关）
│   └── mahjong_config.json       # 疑似麻友识别配置（商户排除关键词、对手方数量范围、最少出现天数）
├── service/pipeline.py         # 管道编排：遍历→读取→清洗→合并→去重→停车识别→特殊交易筛选→麻友识别→群红包识别→输出
├── utils/
│   ├── columns.py              # 自适应列名识别（find_column / find_columns_containing）
│   ├── clean_text.py           # 文本清洗工具
│   ├── config_loader.py        # JSON 配置加载器
│   ├── paths.py                # 路径工具（兼容 PyInstaller）
│   └── logger.py               # 日志（控制台 ANSI 颜色 + 文件）
└── webui/
    ├── bridge.py               # Python → JS API（文件选择、批处理、合并、注册信息清洗、停车/时段/特殊交易配置读写）
    └── static/                 # React 前端（本地 JS，无 CDN 依赖）

linux_build/                    # Linux Docker 本地打包（源码，已跟踪）
├── Dockerfile                  # ubuntu:20.04 + Python 3.12 源码编译 + 系统依赖
├── build.sh                    # 宿主机一键入口（docker build + run）
├── _build_inside.sh            # 容器内构建脚本（venv → pip → 4 路 PyInstaller）
└── .dockerignore               # 排除 .venv .git dist 加速构建上下文
```

## 关键设计决策

### 自适应列识别（不硬编码列名/位置）

腾讯返回的字段顺序和名称可能变化。所有列通过 `find_column(columns, keywords)` 关键词匹配定位，要求所有关键词同时出现。例如：
- `find_column(cols, ['交易', '金额', '分'])` 匹配"交易金额(分)"
- `find_column(cols, ['交易', '用途', '类型'])` 匹配"交易用途类型"

同时存在 `find_columns_containing(columns, keywords)` 用于查找所有匹配列。

**语义锚点定位**：新列插入不依赖固定索引。规则：
- 日期/时间 → 插入「交易用途类型」之后
- 进账金额/出账金额 → 插入「交易金额(元)」紧左边

### 清洗流水线

`process_dataframe()` 依次执行：列名清洗 → 合并重复列 → 金额分转元（含余额列） → 拆日期/时间（去前导零，`2026/4/2` 格式） → 拆分进账/出账金额 → 时段分类 → 日期分类。

### 去重策略

联合主键 **用户ID + 交易单号 + 大单号 + 日期 + 时间 + 借贷类型 + 交易金额(元) + 对手方ID**（8 列固定）。加入「对手方ID」避免群红包场景误删——群发红包时多条记录的前 7 列完全相同，仅对手方ID和对手方接收金额不同。某列缺失时从键中排除并 warning；全部缺失 fallback 全列去重。

### Excel 输出格式化

`writer.py` 中 `HIDDEN_COLUMN_KEYWORDS` 定义默认隐藏的列（交易单号、大单号、借贷类型、银行卡号等敏感/冗余字段），`FIXED_WIDTH_COLUMNS` 定义固定列宽的列（用户ID=7、对手方ID=7 等）。通过关键词匹配自适应识别，不硬编码列名。

### 前端零外部依赖

React/Babel 的 `.js` 文件存放在 `webui/static/` 本地（通过 npm 安装后复制），不依赖 CDN（jsdelivr 在国内被墙）。日志面板支持"复制日志"按钮（`navigator.clipboard.writeText` + fallback `execCommand`）。

### 多批次合并

`app_merge.py` 独立工具。将同一案件多次清洗产出的 xlsx 合并并去重——适用于同一数据源在不同日期多次导出、分别清洗后需要汇合的场景。

### 停车缴费识别

在去重后自动识别停车缴费相关记录，提取车牌号，输出到独立工作表「停车缴费」。

**识别规则**（优先级从高到低）：
1. 「备注2」或「备注1」列包含任一配置关键词（如"停车缴费""停车费""停车""停车场""临停缴费"），且不含任一排除关键词
2. 「对手侧账户名称」列包含"停车"

**车牌提取**：从「备注2」优先提取，失败则尝试「备注1」。正则匹配「省份简称 + 字母 + 5~6 位字母数字」，允许 `-` 穿插。优先 5 位（标准蓝牌），6 位仅当上下文合理时取（新能源绿牌）。无法识别的填"无"。

**标黄规则**：仅当同时满足以下条件时整行标黄（供人工复核）：
- 车牌 = "无"（正则未能提取）
- 备注2 或 备注1 中包含省份简称（说明文本中确实提到了车牌号，但提取逻辑有遗漏）

如果备注中有停车关键词但无省份简称（说明备注本身就没写车牌号），则不标黄。

**配置**：`scripts/config/parking_config.json`，可通过 GUI「⚙️ 停车配置」Tab 直观增删关键词（含筛选逻辑流程图），也可直接编辑 JSON 文件。

**输出**：Excel 新增「停车缴费」工作表，格式与汇总表一致（隐藏列、固定列宽、冻结表头）。内部辅助列 `_备注含省份简称` 自动隐藏。

### 时段分类

在清洗流水线末尾（进账/出账拆分之后），根据"时间"列自动将交易归类到不同时段。新增"时段"列追加到明细表最右侧（"备注2"之后）。

**匹配规则**：
- 将时间字符串（`HH:MM` / `HH:MM:SS`）解析为分钟数（0~1439）
- 按配置的时段数组顺序匹配，`start ≤ 分钟数 < end` 则命中（start 包含，end 不包含）
- 第一个命中即返回，未命中 → "未知"
- 已存在"时段"列时跳过（幂等）

**默认配置**：凌晨 00:00~06:00 / 早上 06:00~12:00 / 下午 12:00~19:00 / 晚上 19:00~24:00

**冒号归一化**：自动将中文全角冒号 `：` 转为半角 `:`，兼容中英文输入法。

**配置**：`scripts/config/time_period_config.json`，可通过 GUI「⏰ 时段配置」Tab 增删改时段（名称 + 起止时间），也可直接编辑 JSON 文件。

**GUI 管道覆盖**：多批次合并管道（`bridge.py` start_merge_process）去重后同样调用 `classify_time_period()`。

### 日期分类

在时段分类之后，根据"日期"列自动区分工作日/节假日/周末。新增"日期分类"列追加到明细表最右侧（"时段"之后）。

**依赖**：`chinesecalendar` 库（PyPI），提供国务院公布的节假日数据（覆盖 2004~2030 年）。

**分类逻辑**：
- 调用 `get_holiday_detail(date)` 判断：
  - `is_holiday=True` 且 `name` 非空 → `节假日（春节）`  # 标注具体节日名称
  - `is_workday=True` → `工作日`  # 含调休上班的周末
  - 两者皆否 → `周末`  # 普通周六日
- `name=None` 的假期（chinesecalendar 将普通周末也标记为 is_holiday）归类为"周末"，不显示为"节假日"。
- 已存在"日期分类"列时跳过（幂等）

**⚡ 性能**：先对唯一日期（≤365个/年）缓存分类结果，再 map 到全量行，几十万行数据无压力。

**节日名称映射**：chinesecalendar 仅返回英文名称（如 "Spring Festival"），`processor.py` 内置 `_HOLIDAY_NAME_MAP` 做英→中翻译（春节/元旦/清明/劳动节/端午/中秋/国庆）。

### 特殊交易筛选

在去重后自动筛选情感数字、特殊日期、特殊备注记录，输出到独立工作表「特殊交易」。参照停车缴费模块模式（`parking.py`），实现在 `special_filter.py`。

**筛选规则**（OR 关系，满足任一即命中）：
1. **2月14日**：解析"日期"列，month=2 且 day=14
2. **交易金额含情感数字**：金额（元）格式化为 2 位小数字符串，检查是否**包含**配置中的金额模式（如 `999` 匹配 `999.99`、`520` 匹配 `520.00`）
3. **备注2含特殊关键词**：包含任一配置中的备注关键词

**⚡ 性能**：全部使用 pandas 向量化操作（`str.contains`、`pd.to_datetime`），不逐行 apply。

**配置**：`scripts/config/special_filter_config.json`，包含 `金额模式`、`备注关键词`、`启用2月14日` 三个字段，可直接编辑 JSON 调整规则，无需改代码。

**输出**：Excel 新增「特殊交易」工作表，格式与汇总表一致（隐藏列、固定列宽、冻结表头）。空 DataFrame 时不创建该工作表。

**管道覆盖**：
- `pipeline.py` 单批次管道：去重后 → 停车识别 → 特殊交易筛选 → 麻友识别 → 群红包识别 → 输出
- `bridge.py` 合并管道：去重后 → 时段分类 → 停车识别 → 特殊交易筛选 → 麻友识别 → 群红包识别 → 输出

### 疑似麻友识别

在去重后自动识别潜在麻将朋友（麻友），输出到独立工作表「疑似麻友」。参照停车缴费/特殊交易模块模式，实现在 `mahjong.py`。

**识别规则**（所有条件必须同时满足）：
1. **晚间时段**：时间 ≥ 20:00 或 < 06:00（凌晨归前一日晚间 session）
2. **转账类型**：「交易用途类型」精确等于"转账"
3. **红包/转账备注**：「备注1」精确等于"微信红包"或"微信转账"
4. **自然人对手方**：「对手侧账户名称」不含任一商户关键词（公司、店、超市、酒店等 50+ 关键词）
5. **麻将场景**：同一晚间 session 内，发送方与 2-10 个不同对手方交易
6. **跨日重复**：同一对手方在 ≥2 个不同晚间出现 → 标记为"疑似麻友"

**Evening Session 定义**：
- 时间 20:00-23:59 → session_date = 当天日期
- 时间 00:00-05:59 → session_date = 日期 - 1 天（归属前一日晚间）

**嫌疑等级分档**：
- 高（≥5天）/ 中（3-4天）/ 低（2天）

**自然人对判断**：排除法。「对手侧账户名称」包含任一商户关键词（公司、店、餐饮、酒店、物业、医院、培训、科技等 50+ 词）→ 视为商户，予以排除。

**输出格式**：
- **交易明细**：原始列 + `_对手方出现天数`（辅助列，自动隐藏）+ `_嫌疑等级`
- **总体统计**：明细下方空 2 行，列出嫌疑人名称、关联用户、出现天数、交易笔数、涉及总金额、最高单笔金额（按出现天数降序）

**配置**：`scripts/config/mahjong_config.json`，包含 `商户排除关键词`、`单晚最少/最多对手方数`、`最少出现天数`、`备注1匹配`、`交易用途类型匹配`。

**⚡ 性能**：先通过"时段"列快速过滤（晚上/凌晨），再用时间列精确判断；商户关键词向量化排除；pandas groupby 统计。

### 群红包识别

在去重后自动识别群红包记录（同一时刻向多人发微信红包），输出到独立工作表「群红包记录」和「群红包-统计」。参照麻友模块模式，实现在 `group_red_packet.py`。

**识别规则**（所有条件必须同时满足）：
1. **备注1**：精确等于"微信红包"
2. **出账金额 > 0**：只取支出记录
3. **时间戳聚类**：同一（日期 + 时间）出现 ≥2 条记录（群红包特征：同一时刻多人收款）
4. **金额关系**：对手方接收金额(元) < 出账金额（排除 1对1 红包，金额相等说明非拆分）

**不需要配置文件**：规则固定简单，无需外部配置。

**输出格式**：
- **群红包记录**：满足条件的交易明细（原始列），格式与汇总表一致（隐藏列、固定列宽、冻结表头）
- **群红包-统计**：按对手方汇总 — 用户侧账号名称、对手方ID、对手侧账户名称、对手方收款次数、对手方接收金额(元)累计（按累计金额倒序）

**⚡ 性能**：全部向量化操作（`str.strip`、`pd.to_numeric`、`groupby.transform`），无逐行 apply。

**管道覆盖**：
- `pipeline.py` 单批次管道：去重后 → … → 麻友识别 → 群红包识别 → 输出
- `bridge.py` 合并管道：同上
- `app_merge.py` CLI 合并：同上

### 注册信息提取合并

`app_reg.py` 独立工具。遍历目录树中所有 `TenpayRegInfo.txt`，提取注册信息（账户状态、账号、姓名、身份证号、绑定手机等），合并去重后输出三 sheet Excel。

**TenpayRegInfo.txt 格式**（UTF-8 + Tab 分隔，两区域）：
- **区域一（基本信息表）**：表头（9列：账户状态/账号/注册姓名/注册时间/注册身份证号/绑定手机/绑定状态/开户行信息/银行账号）+ 主记录行 + 可选银行卡扩展行（前6列为空）
- **区域二（注销/变更信息表）**：表头（9列：账号/注册姓名/注册身份证号/注册时间/注销时间/开户行信息/银行账号/绑定时间/解绑时间）+ 历史记录

**账户状态**：
- `正常`（~81%）：活跃账户，完整信息 + 银行卡记录
- `已注销`（~8%）：仅状态+账号有值，注销区有注销记录
- `未注册`（~1%）：标准表头格式，仅状态+账号有值
- `账号不存在`（~9%）：单行特殊格式 — "账号XXX不存在"

**变更类型识别**：
- `身份信息变更`：状态=正常 + 注销区有数据 → 旧身份→新身份
- `账户注销`：状态=已注销 + 注销区有数据 → 注销记录

**输出 Excel**（三 sheet）：
- Sheet「注册信息汇总」：去重后的主记录（按 账号+身份证号 去重），含数据来源和调证编号
- Sheet「变更记录」：所有变更/注销历史，含变更类型、当前/旧身份对照
- Sheet「基础信息」：自然人基础信息（`build_person_info()` 从汇总表抽唯一身份）

**设计约束**：银行账号相关字段（开户行信息、银行账号）不参与合并清洗，直接透传。

**GUI 集成**：单批次清洗页提供「同时清洗注册信息」勾选框（默认勾选）。勾选后，交易流水处理完成后自动在同目录输出 `TenpayRegInfo_merge.xlsx`。输入/输出文件夹复用交易流水的选择，无需额外配置。注册信息清洗速度快（~0.6秒/164文件），不单独设立 Tab。

## 注意事项

- 虚拟环境 `.venv` 在项目根目录，VS Code 不会自动选中，需 `Ctrl+Shift+P → Python: Select Interpreter` 手动选择
- 每次 Claude Code 的 Shell 调用都是全新会话，不会自动激活 venv。给 venv 装包用绝对路径：`& ".\.venv\Scripts\pip.exe" install <pkg>`
- 首次部署安装依赖：`& ".\.venv\Scripts\pip.exe" install -r requirements.txt`
- 仅处理 `.txt` 文件，忽略 `.xlsx`（src_ref 中的 xlsx 是旧脚本的二次产物，非原始数据）
- `scripts/Tenpay_merge_v2.0.py` 是原始单文件脚本，保留作为参考
- `requirements.txt` 位于项目根目录，记录所有直接依赖
- **版本号**统一在 `scripts/version.py`（`VERSION = "4.1"`），所有入口（`app.py`/`app_merge.py`/`app_reg.py`/`gui_app.py`/`bridge.py`）从此动态读取，前端通过 `get_version()` API 获取。`.spec`/`index.html`/`style.css` 中的版本引用仅作注释，不参与构建逻辑
- `.gitattributes` 强制 `*.sh` 和 `Dockerfile` 使用 LF 行尾，确保 Linux 容器兼容

## 打包构建

### Windows exe

```powershell
pyinstaller --onefile --name tenpaytrade-gui --paths scripts `
  --add-data "scripts/config;scripts/config" `
  --add-data "scripts/utils;scripts/utils" `
  --add-data "scripts/webui/static;scripts/webui/static" `
  --hidden-import=utils.paths `
  --hidden-import=webview.platforms.edgechromium `
  --hidden-import=tkinter scripts/gui_app.py
```

### Linux 可执行文件（Docker 本地构建）

**前置条件**：安装 Docker Desktop 并启动。

```bash
# 项目根目录运行（Git Bash 或 WSL）
bash linux_build/build.sh
```

产物输出到 `dist/`：`tenpaytrade` / `tenpaytrade-merge` / `tenpaytrade-reg` / `tenpaytrade-gui` / `启动工具.sh`。GLIBC 锁定 2.31（ubuntu:20.04），兼容 Ubuntu 20.04+。

### 构建经验（踩坑记录）

1. **Docker Desktop 镜像源**：国内需配置可用 mirror。项目默认使用 `docker.1ms.run` + `docker.xuanyuan.me`。如果拉取失败，检查 `~/.docker/daemon.json` 中的 `registry-mirrors`，重启 Docker Desktop 生效。

2. **deadsnakes PPA 不可用**：从国内访问 `ppa.launchpad.net` 经常超时，Dockerfile 改用**从源码编译 Python 3.12**，源码包通过 `registry.npmmirror.com`（淘宝 NPM 镜像）下载。编译耗时 ~4 分钟，但 Docker 层缓存后首次构建即永久生效。

3. **PyInstaller 6.x `--add-data` 格式**：Linux 下用冒号分隔 `SRC:DEST`，DEST 必须是**相对路径**。正确格式：
   ```bash
   --add-data "/project/scripts/config:scripts/config"   # ✅ DEST 相对
   --add-data "/project/scripts/config:/project/scripts/config"  # ❌ DEST 绝对，PyInstaller 6.x 报错
   ```

4. **Git Bash 路径映射问题**：`docker run -v "$PROJECT_DIR:/project"` 在 Git Bash 中可能因 MSYS2 路径转换导致挂载失败。改用 **PowerShell 直接运行 Docker 命令**更可靠：
   ```powershell
   docker run --rm -v "C:\CCProject\tenpaytrade_merge:/project" tenpaytrade-builder bash /project/linux_build/_build_inside.sh
   ```

5. **PowerShell 误报错误**：Docker/PyInstaller 输出到 stderr 时，PowerShell 会标记为红色 `NativeCommandError`，实际构建成功。判断标准是看 `Build complete!` 和 `exit code 0`。

6. **`dist/` 已 gitignore**：构建产物不跟踪。`linux_build/` 是源码（Dockerfile + 脚本），**应提交跟踪**。

7. **`chinesecalendar` hidden import 警告**：PyInstaller 报 `Hidden import 'chinesecalendar' not found`，但实际通过正常 import 链（processor.py → pipeline.py → gui_app.py）自动发现，不影响功能。`user32`/`msvcrt` 警告同理（Windows 库，Linux 忽略即可）。
