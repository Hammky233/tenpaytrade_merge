#!/bin/bash
# ============================================================================
# Linux 本地打包 — 一键构建脚本（宿主机入口）
#
# 前置条件：Docker Desktop 已安装并运行
# 使用方法：
#   bash linux_build/build.sh          # 在项目根目录运行
#   bash linux_build/build.sh --no-cache  # 强制重新构建镜像
#
# 产物输出到 dist/ 目录：
#   tenpaytrade           CLI 单批次交易流水清洗
#   tenpaytrade-merge     CLI 多批次合并去重
#   tenpaytrade-reg       CLI 注册信息提取
#   tenpaytrade-gui       GUI 图形界面
#   启动工具.sh            启动脚本（含系统依赖检查）
#
# 目标兼容性：GLIBC 2.31+ (Ubuntu 20.04+)
# ============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_NAME="tenpaytrade-builder"
CACHE_ARG=""

# 解析参数
for arg in "$@"; do
    case $arg in
        --no-cache)
            CACHE_ARG="--no-cache"
            echo "⚠️  强制重新构建 Docker 镜像（--no-cache）"
            ;;
        --help|-h)
            echo "用法: bash linux_build/build.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --no-cache    强制重新构建 Docker 镜像"
            echo "  --help, -h    显示此帮助信息"
            exit 0
            ;;
    esac
done

cd "$PROJECT_DIR"

# ── 检查 Docker ──
if ! command -v docker &> /dev/null; then
    echo "❌ 未找到 Docker 命令"
    echo ""
    echo "请先安装 Docker Desktop："
    echo "  https://www.docker.com/products/docker-desktop/"
    echo ""
    echo "或者使用 WSL2 备选方案，参考 docs/linux_deploy.md"
    exit 1
fi

if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未运行，请先启动 Docker Desktop"
    exit 1
fi

# ── 显示版本 ──
VERSION=$(python3 -c "import sys; sys.path.insert(0, '$PROJECT_DIR/scripts'); from version import VERSION; print(VERSION)" 2>/dev/null || echo "4.1")
echo "========================================="
echo "  财付通交易流水处理工具 — Linux 打包"
echo "  版本: v${VERSION}"
echo "  目标环境: ubuntu:20.04 (GLIBC 2.31)"
echo "========================================="
echo ""

# ── 构建 Docker 镜像 ──
echo "[1/2] 构建 Docker 镜像 ($IMAGE_NAME)..."
docker build $CACHE_ARG -t "$IMAGE_NAME" "$SCRIPT_DIR"
echo ""
echo "✅ Docker 镜像就绪"

# ── 运行容器执行构建 ──
echo ""
echo "[2/2] 容器内构建（产物输出到 dist/）..."
echo ""

# 容器以当前用户 UID 运行，确保产物权限正确
docker run --rm \
    -v "$PROJECT_DIR:/project" \
    -e "HOST_UID=$(id -u)" \
    -e "HOST_GID=$(id -g)" \
    "$IMAGE_NAME" \
    bash /project/linux_build/_build_inside.sh

# ── 修正文件权限（容器内是 root，可能导致文件属主不对）──
if [ "$(uname)" != "Darwin" ] && [ "$(uname)" != "MINGW"* ] && [ "$(uname)" != "MSYS"* ]; then
    # Linux 宿主机：修正权限
    chown -R "$(id -u):$(id -g)" "$PROJECT_DIR/dist" 2>/dev/null || true
fi
# macOS / Git Bash 不需要 chown（Docker Desktop 自动处理）

echo ""
echo "========================================="
echo "  ✅ Linux 打包完成!"
echo "  产物目录: $PROJECT_DIR/dist/"
echo "========================================="
echo ""
echo "可执行文件:"
ls -lh "$PROJECT_DIR/dist/"
echo ""
echo "下一步："
echo "  1. 将 dist/ 目录复制到 Ubuntu 20.04+ 机器"
echo "  2. chmod +x dist/tenpaytrade*"
echo "  3. ./dist/tenpaytrade --help 验证"
echo ""
