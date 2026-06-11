# Linux 构建环境 — ubuntu:20.04 (GLIBC 2.31)
# 与 GitHub Actions build-linux.yml 环境对齐
FROM ubuntu:20.04

# 避免 apt 安装时弹出时区交互
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# 替换为阿里云镜像源（中国大陆加速）
RUN sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list

# 系统依赖（一次性安装，含编译 Python 所需的 build-essential 和 tk 依赖）
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libssl-dev \
        zlib1g-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        libffi-dev \
        liblzma-dev \
        tk-dev \
        python3-tk \
        libgtk-3-0 \
        libwebkit2gtk-4.0-37 \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 从源码编译 Python 3.12（不依赖 PPA，纯阿里云下载）
# Python 源码使用淘宝 NPM 镜像加速
ARG PYTHON_VERSION=3.12.3
ENV PYTHON_CONFIGURE_OPTS="--enable-optimizations --with-lto"

RUN curl -fsSL -o /tmp/Python-${PYTHON_VERSION}.tgz \
        "https://registry.npmmirror.com/-/binary/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz" \
    && cd /tmp \
    && tar -xzf Python-${PYTHON_VERSION}.tgz \
    && cd Python-${PYTHON_VERSION} \
    && ./configure \
        --enable-optimizations \
        --enable-shared \
        --prefix=/usr/local \
        LDFLAGS="-Wl,-rpath,/usr/local/lib" \
    && make -j$(nproc) \
    && make altinstall \
    && cd / && rm -rf /tmp/Python-${PYTHON_VERSION} /tmp/Python-${PYTHON_VERSION}.tgz

# 设置 Python 3.12 为默认 python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/local/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/pip3 pip3 /usr/local/bin/pip3.12 1

# pip 阿里云镜像
RUN python3 -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    python3 -m pip config set global.trusted-host mirrors.aliyun.com

WORKDIR /project
