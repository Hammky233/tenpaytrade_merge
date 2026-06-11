# Linux 部署指南

财付通交易流水处理工具 v4.1 支持在 Linux 系统上运行。

## 系统要求

- Python 3.10+
- Ubuntu 20.04+ / Debian 11+ / CentOS 8+ / 或其他主流发行版
- 桌面环境（GUI 模式需要）

## 一、安装 Python 虚拟环境

```bash
# 克隆或复制项目到 Linux
cd /path/to/tenpaytrade_merge

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装 Python 依赖
pip install -r requirements.txt
```

## 二、CLI 模式（无需桌面环境）

CLI 模式不需要任何系统级依赖，`pip install -r requirements.txt` 即可运行：

```bash
# 单批次清洗
python scripts/app.py -s /path/to/source_data -o /path/to/output

# 多批次合并
python scripts/app_merge.py -i batch1.xlsx batch2.xlsx -o merged.xlsx
```

## 三、GUI 模式（需要桌面环境）

### 3.1 安装系统依赖

**Ubuntu/Debian：**

```bash
# tkinter（文件选择对话框）
sudo apt install python3-tk

# pywebview GTK 后端（推荐）
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1

# 或者使用 Qt 后端
# sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine
```

**Fedora：**

```bash
sudo dnf install python3-tkinter webkit2gtk3
```

**Arch Linux：**

```bash
sudo pacman -S tk webkit2gtk
```

### 3.2 启动 GUI

```bash
source .venv/bin/activate
python scripts/gui_app.py
```

## 四、常见问题

### Q: 启动 GUI 时报 `No module named 'tkinter'`
安装 `python3-tk`：`sudo apt install python3-tk`

### Q: 启动 GUI 时报 webview 相关错误
确保安装了 GTK3 和 WebKit2 系统库（见 3.1）。也可尝试切换后端：
```python
import webview
# 在 gui_app.py 的 webview.start() 前指定后端
webview.start(gui='gtk')  # 或 'qt'
```

### Q: 中文乱码
确认系统已安装中文字体：
```bash
sudo apt install fonts-noto-cjk
```

## 五、打包分发（PyInstaller）

### 5.1 本地 Docker 构建（推荐 ✅）

使用 Docker 在本地构建 Linux 可执行文件，无需 GitHub Actions，产物兼容 GLIBC 2.31+（Ubuntu 20.04+）。

**前置条件**：安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/) 并启动。

**一键构建**（在项目根目录运行）：

```bash
bash linux_build/build.sh
```

**构建产物**（输出到 `dist/` 目录）：

| 文件 | 大小 | 用途 |
|------|------|------|
| `tenpaytrade` | ~30 MB | CLI 单批次交易流水清洗 |
| `tenpaytrade-merge` | ~30 MB | CLI 多批次合并去重 |
| `tenpaytrade-reg` | ~30 MB | CLI 注册信息提取 |
| `tenpaytrade-gui` | ~60 MB | GUI 图形界面 |
| `启动工具.sh` | ~1 KB | 启动脚本（含系统依赖检查） |

**工作原理**：
1. `build.sh` 构建 `ubuntu:20.04` Docker 镜像（预装 Python 3.12 + 系统依赖）
2. 容器挂载项目目录，在容器内执行 PyInstaller 打包
3. 产物通过 volume 映射输出到宿主机 `dist/` 目录
4. GLIBC 锁定在 2.31，确保与 Ubuntu 20.04+ 兼容

**Docker Hub 不可用？** 脚本已配置阿里云/清华镜像源，无需科学上网。

**清理中间产物**：
```bash
# 中间产物（build/ *.spec）自动清理，仅保留 dist/
```

### 5.2 原生 PyInstaller（本地 Python 环境）

如果已有 Python 3.10+ 环境，也可直接打包：

```bash
pip install pyinstaller

# CLI — 单批次清洗
pyinstaller --onefile --name tenpaytrade \
    --paths scripts \
    --add-data "scripts/config:scripts/config" \
    --add-data "scripts/utils:scripts/utils" \
    --hidden-import=chinesecalendar \
    --hidden-import=utils.paths \
    scripts/app.py

# CLI — 多批次合并
pyinstaller --onefile --name tenpaytrade-merge \
    --paths scripts \
    --add-data "scripts/utils:scripts/utils" \
    --hidden-import=utils.paths \
    scripts/app_merge.py

# CLI — 注册信息提取
pyinstaller --onefile --name tenpaytrade-reg \
    --paths scripts \
    --add-data "scripts/utils:scripts/utils" \
    --hidden-import=utils.paths \
    scripts/app_reg.py

# GUI
pyinstaller --onefile --name tenpaytrade-gui \
    --paths scripts \
    --add-data "scripts/config:scripts/config" \
    --add-data "scripts/utils:scripts/utils" \
    --add-data "scripts/webui/static:scripts/webui/static" \
    --hidden-import=chinesecalendar \
    --hidden-import=utils.paths \
    --hidden-import=webview \
    --hidden-import=webview.platforms.cef \
    --hidden-import=webview.platforms.gtk \
    --hidden-import=webview.platforms.qt \
    --hidden-import=tkinter \
    scripts/gui_app.py
```

> **注意**：PyInstaller 打包的可执行文件只能在相同或更新的 GLIBC 版本上运行。建议在目标系统的最低支持版本上执行打包。若目标为 Ubuntu 20.04（GLIBC 2.31），请使用 Docker 构建方式以确保兼容性。

## 六、Windows ↔ Linux 数据交换注意

- 数据文件（`TenpayTrades.txt`）使用 UTF-8 编码，两端通用
- 输出 Excel 文件使用 openpyxl 引擎，两端完全兼容
- 配置文件（`config/*.json`）均为 UTF-8，直接复用
- **路径分隔符**：代码使用 `os.path.join` / `os.path.sep`，自动适配
