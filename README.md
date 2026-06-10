# 财付通交易流水处理工具 v4.0

批量清洗财付通（Tenpay）交易流水数据。从目录树中读取 `TenpayTrades.txt`（UTF-8 + Tab 分隔），清洗转换后合并输出为一个 Excel 文件，支持多批次合并去重。

## ✨ 功能

- **📂 自适应列识别** — 不硬编码列名/位置，关键词组合匹配腾讯返回的可变字段
- **🧹 自动清洗** — BOM 移除、重复列合并、金额分→元、时间拆分、进账/出账拆分、特殊 Unicode 字符清理
- **🔄 智能去重** — 交易单号 + 大单号联合主键，覆盖率 < 50% 时自动降级
- **🅿️ 停车缴费识别** — 关键词匹配 + 正则提取车牌号，输出独立工作表
- **💝 特殊交易筛选** — 情感数字（520/1314）、2 月 14 日、特殊备注关键词
- **⏰ 时段分类** — 凌晨/早上/下午/晚上，可自定义
- **📅 日期分类** — 工作日/周末/节假日（标注节日名称，如"春节"）
- **📊 Excel 输出** — 列宽自适应、敏感列自动隐藏、停车标黄提示人工复核

## 🚀 快速开始

### Windows（打包好的 exe）

直接运行 `tenpaytrade-gui.exe`，通过图形界面选择文件夹、点击处理即可。

### 开发环境

```powershell
# 1. 克隆仓库
git clone https://github.com/Hammky233/tenpaytrade_merge.git
cd tenpaytrade_merge

# 2. 创建虚拟环境 + 安装依赖
python -m venv .venv
& ".\.venv\Scripts\pip.exe" install -r requirements.txt

# 3. 运行 CLI（单批次）
python scripts/app.py -s <数据源目录> -o <输出目录>

# 4. 运行 CLI（多批次合并）
python scripts/app_merge.py -i batch1.xlsx batch2.xlsx -o merged.xlsx

# 5. 运行 GUI
python scripts/gui_app.py
```

### Linux

CI 自动构建 Linux 可执行文件（GLIBC 2.31 兼容），从 [Actions](https://github.com/Hammky233/tenpaytrade_merge/actions) 页面下载 `tenpaytrade-linux` artifact：

```bash
chmod +x 启动工具.sh tenpaytrade tenpaytrade-merge tenpaytrade-gui
./启动工具.sh   # GUI 模式（需要 GTK3 + WebKit2）
./tenpaytrade -s 数据目录 -o 输出目录   # CLI 模式（无需桌面环境）
```

详细使用指南见 [`docs/linux_usage_guide.md`](docs/linux_usage_guide.md)。

## 📂 数据目录结构

```
案件数据/
├── 张三/
│   ├── wxid_abc123/
│   │   └── TenpayTrades.txt
│   └── wxid_def456/
│       └── TenpayTrades.txt
├── 李四/
│   └── wwwwbbb/
│       └── TenpayTrades.txt
└── ...
```

工具自动递归扫描所有 `TenpayTrades.txt`，嵌套层级不限。

## 📋 输出说明

| 工作表 | 内容 |
|--------|------|
| **财付通交易汇总** | 全部交易记录（已清洗、去重） |
| **停车缴费** | 自动识别的停车缴费记录 |
| **特殊交易** | 情感数字/特殊日期/特殊备注记录 |

汇总表包含：日期、时间、时段、日期分类、交易金额(元)、进账/出账金额、交易用途类型、备注等。敏感列（卡号、单号等）默认隐藏。

## ⚙️ 配置

| 文件 | 用途 |
|------|------|
| `scripts/config/parking_config.json` | 停车识别：关键词、排除词、车牌省份简称 |
| `scripts/config/time_period_config.json` | 时段分类：时段名称、起止时间 |
| `scripts/config/special_filter_config.json` | 特殊交易筛选：金额模式、备注关键词、2/14 开关 |

可通过 GUI 配置面板修改，也可直接编辑 JSON 文件。

## 🏗️ 架构

```
scripts/
├── app.py / app_merge.py       # CLI 入口
├── gui_app.py                  # GUI 入口（pywebview + React）
├── core/
│   ├── reader.py               # txt 读取 + 自动编码检测
│   ├── processor.py            # 清洗流水线（列→金额→时间→拆分→时段→日期）
│   ├── merger.py               # 多 DataFrame 合并 + 智能去重
│   ├── parking.py              # 停车缴费识别 + 车牌提取
│   ├── special_filter.py       # 特殊交易筛选
│   └── writer.py               # Excel 输出 + 格式化
├── service/
│   └── pipeline.py             # 管道编排 + 后处理分析
├── utils/
│   ├── columns.py              # 自适应列名匹配
│   ├── clean_text.py           # 特殊 Unicode 字符清理
│   ├── config_loader.py        # 统一 JSON 配置加载
│   ├── logger.py               # 日志（ANSI 颜色 + 文件）
│   └── paths.py                # 路径工具（开发 + PyInstaller）
├── config/                     # JSON 配置文件
└── webui/
    ├── bridge.py               # Python → JS API
    └── static/                 # React 前端（本地文件，无 CDN 依赖）
```

## 🧪 技术栈

| 技术 | 用途 |
|------|------|
| Python 3.12+ | 核心语言 |
| pandas | 数据处理 |
| openpyxl | Excel 读写 |
| pywebview | 桌面 GUI 窗口 |
| React + Babel | GUI 前端（零外部依赖） |
| chinesecalendar | 节假日判断 |
| PyInstaller | 打包 exe / Linux 可执行文件 |
| GitHub Actions | CI 自动构建 Linux 二进制文件 |

## 📦 本地打包

```powershell
# Windows exe
pip install pyinstaller
pyinstaller --onefile --name tenpaytrade-gui --paths scripts `
  --add-data "scripts/config;scripts/config" `
  --add-data "scripts/utils;scripts/utils" `
  --add-data "scripts/webui/static;scripts/webui/static" `
  --hidden-import=chinesecalendar --hidden-import=utils.paths `
  scripts/gui_app.py
```

## 📄 许可

MIT
