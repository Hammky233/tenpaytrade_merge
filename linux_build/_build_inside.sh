#!/bin/bash
# ============================================================================
# 容器内构建脚本（由 build.sh 通过 docker run 调用）
# 在 ubuntu:20.04 环境中执行 PyInstaller 打包
# ============================================================================
set -e

PROJECT_DIR="/project"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
DIST_DIR="$PROJECT_DIR/dist"

cd "$PROJECT_DIR"

# ── 读取版本号 ──
VERSION=$(python3 -c "import sys; sys.path.insert(0, '$SCRIPTS_DIR'); from version import VERSION; print(VERSION)")
echo "========================================="
echo "  财付通交易流水处理工具 — Linux 构建"
echo "  版本: v${VERSION}"
echo "  目标 GLIBC: 2.31"
echo "========================================="
echo ""

# ── 创建虚拟环境 ──
echo "[1/5] 创建 Python 虚拟环境..."
python3 -m venv /tmp/build_venv
source /tmp/build_venv/bin/activate
echo "Python: $(python3 --version)"

# ── 安装依赖 ──
echo ""
echo "[2/5] 安装 Python 依赖..."
# 升级 pip（使用镜像源）
pip install --upgrade pip -q
pip install -r "$PROJECT_DIR/requirements.txt" -q
pip install pyinstaller -q
echo "PyInstaller: $(pyinstaller --version)"

# ── 清理旧产物 ──
echo ""
echo "[3/5] 清理旧产物..."
rm -rf "$DIST_DIR" "$PROJECT_DIR/build"
mkdir -p "$DIST_DIR"

# ── 构建 ──
echo ""
echo "[4/5] 开始 PyInstaller 打包..."

# 4.1 CLI — 单批次交易流水清洗
echo ""
echo "  [4.1/4] CLI 单批次清洗 (tenpaytrade)..."
pyinstaller \
    --onefile \
    --name tenpaytrade \
    --paths "$SCRIPTS_DIR" \
    --add-data "$SCRIPTS_DIR/config:scripts/config" \
    --add-data "$SCRIPTS_DIR/utils:scripts/utils" \
    --hidden-import=chinesecalendar \
    --hidden-import=utils.paths \
    "$SCRIPTS_DIR/app.py" \
    --distpath "$DIST_DIR" --workpath "$PROJECT_DIR/build/app" --specpath "$PROJECT_DIR/build"
echo "    → dist/tenpaytrade 完成"

# 4.2 CLI — 多批次合并
echo ""
echo "  [4.2/4] CLI 多批次合并 (tenpaytrade-merge)..."
pyinstaller \
    --onefile \
    --name tenpaytrade-merge \
    --paths "$SCRIPTS_DIR" \
    --add-data "$SCRIPTS_DIR/utils:scripts/utils" \
    --hidden-import=utils.paths \
    "$SCRIPTS_DIR/app_merge.py" \
    --distpath "$DIST_DIR" --workpath "$PROJECT_DIR/build/merge" --specpath "$PROJECT_DIR/build"
echo "    → dist/tenpaytrade-merge 完成"

# 4.3 CLI — 注册信息提取（v4.1 新增）
echo ""
echo "  [4.3/4] CLI 注册信息提取 (tenpaytrade-reg)..."
pyinstaller \
    --onefile \
    --name tenpaytrade-reg \
    --paths "$SCRIPTS_DIR" \
    --add-data "$SCRIPTS_DIR/utils:scripts/utils" \
    --hidden-import=utils.paths \
    "$SCRIPTS_DIR/app_reg.py" \
    --distpath "$DIST_DIR" --workpath "$PROJECT_DIR/build/reg" --specpath "$PROJECT_DIR/build"
echo "    → dist/tenpaytrade-reg 完成"

# 4.4 GUI
echo ""
echo "  [4.4/4] GUI (tenpaytrade-gui)..."
pyinstaller \
    --onefile \
    --name tenpaytrade-gui \
    --paths "$SCRIPTS_DIR" \
    --add-data "$SCRIPTS_DIR/config:scripts/config" \
    --add-data "$SCRIPTS_DIR/utils:scripts/utils" \
    --add-data "$SCRIPTS_DIR/webui/static:scripts/webui/static" \
    --hidden-import=chinesecalendar \
    --hidden-import=utils.paths \
    --hidden-import=webview \
    --hidden-import=webview.platforms.cef \
    --hidden-import=webview.platforms.gtk \
    --hidden-import=webview.platforms.qt \
    --hidden-import=tkinter \
    "$SCRIPTS_DIR/gui_app.py" \
    --distpath "$DIST_DIR" --workpath "$PROJECT_DIR/build/gui" --specpath "$PROJECT_DIR/build"
echo "    → dist/tenpaytrade-gui 完成"

# ── 生成启动脚本 ──
echo ""
echo "[5/5] 生成启动脚本..."
cat > "$DIST_DIR/启动工具.sh" << SCRIPTEOF
#!/bin/bash
# 财付通交易流水处理工具 — 启动脚本 v${VERSION}
# 自动检查系统依赖，缺失时给出安装提示

SCRIPT_DIR="\$(cd "\$(dirname "\$0")" && pwd)"

echo "========================================="
echo "  财付通交易流水处理工具 v${VERSION}"
echo "========================================="
echo ""

# 检查 GTK3 + WebKit2（GUI 模式需要）
check_lib() {
    local name="\$1"
    local pkg="\$2"
    if ! ldconfig -p 2>/dev/null | grep -q "\$name"; then
        echo "⚠️  缺少系统库: \$name"
        echo "   请运行: sudo apt install \$pkg"
        echo ""
        MISSING=1
    fi
}

MISSING=0
check_lib "libgtk-3" "libgtk-3-0"
check_lib "libwebkit2gtk-4" "libwebkit2gtk-4.0-37"

if [ "\$MISSING" = "1" ]; then
    echo "========================================="
    echo "  一键安装命令（Ubuntu/Debian）："
    echo "  sudo apt install libgtk-3-0 libwebkit2gtk-4.0-37"
    echo "========================================="
    echo ""
    echo "按回车键退出..."
    read -r
    exit 1
fi

echo "✅ 系统依赖检查通过，启动中..."
echo ""

# 启动 GUI
exec "\$SCRIPT_DIR/tenpaytrade-gui"
SCRIPTEOF

chmod +x "$DIST_DIR/启动工具.sh"
echo "    → dist/启动工具.sh 完成"

# ── 清理临时构建文件 ──
rm -rf "$PROJECT_DIR/build" "$PROJECT_DIR"/*.spec

# ── 验证 ──
echo ""
echo "========================================="
echo "  构建完成! — 产物列表"
echo "========================================="
ls -lh "$DIST_DIR/"
echo ""

# 测试 CLI --help
echo "--- tenpaytrade --help ---"
"$DIST_DIR/tenpaytrade" --help 2>&1 | head -5 || true
echo ""
echo "--- tenpaytrade-reg --help ---"
"$DIST_DIR/tenpaytrade-reg" --help 2>&1 | head -5 || true
echo ""
echo "--- GUI 省略验证（需要显示器）---"
echo ""
echo "========================================="
echo "  产物已同步到宿主机的 dist/ 目录"
echo "========================================="
