#!/usr/bin/env python3
"""
财付通交易流水处理工具 v4.0 — GUI 入口（pywebview）
"""

import os
import sys

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import webview
from webui.bridge import Api


def main():
    # 静态文件目录
    static_dir = os.path.join(os.path.dirname(__file__), "webui", "static")
    index_html = os.path.join(static_dir, "index.html")

    if not os.path.exists(index_html):
        print(f"❌ 找不到前端文件: {index_html}")
        sys.exit(1)

    api = Api()

    # 创建窗口
    window = webview.create_window(
        title="财付通交易流水处理工具 v4.0",
        url=index_html,
        js_api=api,
        width=860,
        height=700,
        min_size=(720, 520),
        resizable=True,
        confirm_close=True,
    )

    webview.start(debug=False)


if __name__ == "__main__":
    main()
