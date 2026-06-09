# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

批量清洗财付通（Tenpay）交易流水数据。从目录树中读取 `TenpayTrades.txt`（UTF-8 + Tab 分隔），清洗转换后合并输出为一个 Excel 文件，支持多批次合并去重。

## 常用命令

```powershell
# CLI 单批次清洗
python scripts/app.py -s <数据源目录> -o <输出目录> [-n 文件名]

# CLI 多批次合并（将多次清洗结果合并去重）
python scripts/app_merge.py -i batch1.xlsx batch2.xlsx -o merged.xlsx

# GUI（pywebview + React）
python scripts/gui_app.py
```

示例：
```powershell
python scripts/app.py -s src_ref/0062_L-1780366225387 -o output
python scripts/app_merge.py -i output/batch_0605.xlsx output/batch_0607.xlsx -o output/merged.xlsx
```

## 架构

```
scripts/
├── app.py / app_merge.py       # CLI 入口（单批次 / 多批次合并）
├── gui_app.py                  # pywebview GUI 入口
├── core/
│   ├── reader.py               # txt 读取，自动编码检测，空文件跳过
│   ├── processor.py            # 清洗流水线：列名清洗→合并重复列→分转元→时间拆分→进账/出账
│   ├── merger.py               # 多 DataFrame 合并 + (交易单号+大单号)联合去重
│   ├── parking.py              # 停车缴费识别 + 车牌提取
│   └── writer.py               # Excel 输出 + 列宽自适应（支持停车缴费第二 sheet）
├── config/
│   └── parking_config.json     # 停车识别配置（关键词、排除词、车牌省份简称）
├── service/pipeline.py         # 管道编排：遍历→读取→清洗→合并→去重→停车识别→输出
├── utils/logger.py             # 日志（控制台 ANSI 颜色 + 文件）
└── webui/
    ├── bridge.py               # Python → JS API（pywebview bridge）
    └── static/                 # React 前端（本地 JS，无 CDN 依赖）
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

`process_dataframe()` 依次执行：列名清洗 → 合并重复列 → 金额分转元（含余额列） → 拆日期/时间（去前导零，`2026/4/2` 格式） → 拆分进账/出账金额。

### 去重策略

联合主键 **交易单号 + 大单号**。若某个字段覆盖率 < 50% 则降级为单字段，两个都不足则全列去重。

### Excel 输出格式化

`writer.py` 中 `HIDDEN_COLUMN_KEYWORDS` 定义默认隐藏的列（交易单号、大单号、借贷类型、银行卡号等敏感/冗余字段），`FIXED_WIDTH_COLUMNS` 定义固定列宽的列（用户ID=7、对手方ID=7 等）。通过关键词匹配自适应识别，不硬编码列名。

### 前端零外部依赖

React/Babel 的 `.js` 文件存放在 `webui/static/` 本地（通过 npm 安装后复制），不依赖 CDN（jsdelivr 在国内被墙）。日志面板支持"复制日志"按钮（`navigator.clipboard.writeText` + fallback `execCommand`）。

### 多批次合并

`app_merge.py` 独立工具。将同一案件多次清洗产出的 xlsx 合并并去重——适用于同一数据源在不同日期多次导出、分别清洗后需要汇合的场景。

### 停车缴费识别

在去重后自动识别停车缴费相关记录，提取车牌号，输出到独立工作表「停车缴费」。

**识别规则**（优先级从高到低）：
1. 「备注2」列包含任一配置关键词（如"停车缴费""停车费""停车""停车场""临停缴费"），且不含任一排除关键词
2. 「对手侧账户名称」列包含"停车"

**车牌提取**：正则匹配「省份简称 + 字母 + 5~6 位字母数字」，允许 `-` 穿插。优先 5 位（标准蓝牌），6 位仅当上下文合理时取（新能源绿牌）。无法识别的填"无"并整行标黄。

**配置**：`scripts/config/parking_config.json`，用户可自由增减关键词、排除词、车牌省份简称。

**输出**：Excel 新增「停车缴费」工作表，格式与汇总表一致（隐藏列、固定列宽、冻结表头）。

## 注意事项

- 虚拟环境 `.venv` 在项目根目录，VS Code 不会自动选中，需 `Ctrl+Shift+P → Python: Select Interpreter` 手动选择
- 每次 Claude Code 的 Shell 调用都是全新会话，不会自动激活 venv。给 venv 装包用绝对路径：`& ".\.venv\Scripts\pip.exe" install <pkg>`
- 仅处理 `.txt` 文件，忽略 `.xlsx`（src_ref 中的 xlsx 是旧脚本的二次产物，非原始数据）
- `scripts/Tenpay_merge_v2.0.py` 是原始单文件脚本，保留作为参考
