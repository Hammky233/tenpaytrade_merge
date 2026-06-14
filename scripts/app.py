#!/usr/bin/env python3
"""
财付通交易流水处理工具 — CLI 单批次入口

用法:
    python app.py --source <数据源目录> --output <输出目录> [--name 输出文件名]

示例:
    python app.py --source ../src_ref/0062_L-1780366225387 --output ./output
    python app.py --source ../src_ref/0062_L-1780366225387 --output ./output --name batch_0608.xlsx
"""

import sys
import os
import argparse

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger
from service.pipeline import TenpayPipeline
from version import VERSION, AUTHOR


def main():
    parser = argparse.ArgumentParser(
        description=f"财付通交易流水处理工具 v{VERSION} — 单批次清洗 · {AUTHOR}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python app.py --source ../src_ref/0062_L-1780366225387 --output ./output
  python app.py -s D:/data/20260605 -o D:/result -n batch_0605.xlsx
        """,
    )
    parser.add_argument(
        "-s", "--source",
        required=True,
        help="数据源文件夹路径（包含 TenpayTrades.txt 文件的目录树）",
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="输出文件夹路径",
    )
    parser.add_argument(
        "-n", "--name",
        default="Tenpay_merge.xlsx",
        help="输出 Excel 文件名（默认: Tenpay_merge.xlsx）",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="日志文件输出目录（默认与 output 相同）",
    )

    args = parser.parse_args()

    # 验证路径
    if not os.path.isdir(args.source):
        print(f"❌ 数据源目录不存在: {args.source}")
        sys.exit(1)

    # 初始化日志
    log_dir = args.log_dir or args.output
    logger = setup_logger(log_dir=log_dir)

    logger.info("=" * 60)
    logger.info(f"财付通交易流水处理工具 v{VERSION}（单批次）")
    logger.info(f"制作人: {AUTHOR}")
    logger.info(f"数据源: {args.source}")
    logger.info(f"输出: {os.path.join(args.output, args.name)}")
    logger.info("=" * 60)

    # 执行管道
    pipeline = TenpayPipeline(
        source_dir=args.source,
        output_dir=args.output,
        output_name=args.name,
        log_dir=log_dir,
    )

    result = pipeline.run()

    # 输出摘要
    print()
    print("=" * 60)
    print("处理完成!")
    print(f"  文件总数: {result['total']}")
    print(f"  成功: {result['success']}")
    print(f"  失败: {result['fail']}")
    print(f"  跳过: {result['skipped']}")
    print(f"  总记录: {result['rows']} 行")
    if result['output']:
        print(f"  输出文件: {result['output']}")
    print(f"  耗时: {result.get('elapsed', 'N/A')} 秒")
    print("=" * 60)

    if result['fail'] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
