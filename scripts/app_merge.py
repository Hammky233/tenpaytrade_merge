#!/usr/bin/env python3
"""
财付通交易流水处理工具 — 多批次合并入口

将多次清洗产生的 Excel 文件合并为一个，并去重。

用法:
    python app_merge.py --input batch1.xlsx batch2.xlsx ... --output merged.xlsx

示例:
    python app_merge.py -i ./output/batch_0605.xlsx ./output/batch_0607.xlsx -o ./output/merged.xlsx
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from utils.logger import setup_logger
from core.merger import merge_dataframes, deduplicate
from core.writer import write_excel
from service.pipeline import post_merge_analysis
from version import VERSION, AUTHOR


def main():
    parser = argparse.ArgumentParser(
        description=f"财付通交易流水处理工具 v{VERSION} — 多批次合并 · {AUTHOR}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python app_merge.py -i batch_0605.xlsx batch_0607.xlsx -o merged.xlsx
        """,
    )
    parser.add_argument(
        "-i", "--input",
        nargs="+",
        required=True,
        help="待合并的 Excel 文件列表（至少2个）",
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="输出文件路径（.xlsx）",
    )

    args = parser.parse_args()

    if len(args.input) < 1:
        print("❌ 至少需要1个输入文件")
        sys.exit(1)

    # 验证输入文件
    for f in args.input:
        if not os.path.isfile(f):
            print(f"❌ 文件不存在: {f}")
            sys.exit(1)

    # 初始化日志
    log_dir = os.path.dirname(args.output) or "."
    logger = setup_logger(log_dir=log_dir)

    logger.info("=" * 60)
    logger.info(f"财付通交易流水处理工具 v{VERSION}（多批次合并）")
    logger.info(f"制作人: {AUTHOR}")
    logger.info(f"输入文件: {len(args.input)} 个")
    for i, f in enumerate(args.input, 1):
        logger.info(f"  [{i}] {f}")
    logger.info(f"输出: {args.output}")
    logger.info("=" * 60)

    start = time.time()

    # 1. 读取所有文件
    dfs = []
    for filepath in args.input:
        logger.info(f"读取: {os.path.basename(filepath)}")
        try:
            df = pd.read_excel(filepath, sheet_name="财付通交易汇总", dtype=str)
            dfs.append(df)
            logger.info(f"  → {len(df)} 行, {len(df.columns)} 列")
        except ValueError as e:
            if "not found" in str(e) or "Worksheet named" in str(e):
                logger.error(f"「财付通交易汇总」工作表不存在: {filepath}")
                print(f"❌ 文件缺少必要工作表「财付通交易汇总」: {os.path.basename(filepath)}")
            else:
                logger.error(f"读取失败: {filepath} - {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"读取失败: {filepath} - {e}")
            sys.exit(1)

    # 2. 合并
    logger.info("合并中...")
    merged = merge_dataframes(dfs)
    before = len(merged)
    logger.info(f"合并后: {before} 行")

    # 3. 去重
    merged = deduplicate(merged)
    after = len(merged)

    # 3.5 停车缴费识别 + 特殊交易筛选 + 疑似麻友识别 + 群红包识别
    analysis = post_merge_analysis(merged)
    parking_df = analysis["parking_df"]
    special_df = analysis["special_df"]
    mahjong_df = analysis.get("mahjong_df")
    mahjong_stats_df = analysis.get("mahjong_stats_df")
    mahjong_circle_stats_df = analysis.get("mahjong_circle_stats_df")
    grp_df = analysis.get("grp_df")
    grp_stats_df = analysis.get("grp_stats_df")

    # 4. 输出
    write_excel(merged, args.output,
                parking_df=parking_df, special_df=special_df,
                mahjong_df=mahjong_df, mahjong_stats_df=mahjong_stats_df,
                mahjong_circle_stats_df=mahjong_circle_stats_df,
                grp_df=grp_df, grp_stats_df=grp_stats_df)

    elapsed = time.time() - start

    print()
    print("=" * 60)
    print("合并完成!")
    print(f"  合并前总计: {before} 行")
    print(f"  去重移除:   {before - after} 行")
    print(f"  合并后总计: {after} 行")
    if parking_df is not None:
        print(f"  停车缴费:   {len(parking_df)} 条")
    if mahjong_stats_df is not None and len(mahjong_stats_df) > 0:
        circle_count = len(mahjong_circle_stats_df) if mahjong_circle_stats_df is not None else 0
        print(f"  疑似麻友:   {len(mahjong_stats_df)} 人, {circle_count} 个圈子, {len(mahjong_df)} 条记录")
    if grp_stats_df is not None and len(grp_stats_df) > 0:
        print(f"  群红包:     {len(grp_df)} 条记录, {len(grp_stats_df)} 个对手方")
    print(f"  输出文件:   {args.output}")
    print(f"  耗时:       {elapsed:.1f} 秒")
    print("=" * 60)


if __name__ == "__main__":
    main()
