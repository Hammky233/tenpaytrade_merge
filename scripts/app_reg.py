#!/usr/bin/env python3
"""
财付通注册信息提取合并工具 — CLI 入口

遍历指定文件夹中所有 TenpayRegInfo.txt 文件，提取注册信息（账户状态、账号、
注册姓名、身份证号、绑定手机等），合并去重后输出为 xlsx。

用法:
    python app_reg.py --source <数据源目录> --output <输出目录> [--name 输出文件名]

示例:
    python app_reg.py -s ../src_ref/财付通20260421 -o ./output
    python app_reg.py -s D:/data/reg_info -o D:/result -n 注册信息汇总.xlsx
"""

import sys
import os
import time
import argparse

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger
from core.reg_reader import read_tenpay_reg_info
from core.reg_processor import process_reg_data, build_person_info
from core.writer import write_reg_excel
from version import VERSION, AUTHOR


def _find_reg_files(source_dir: str) -> list[str]:
    """递归扫描 source_dir 下所有 TenpayRegInfo.txt 文件（按路径排序）"""
    from utils.paths import find_files_by_name
    return find_files_by_name(source_dir, "TenpayRegInfo.txt")


def main():
    parser = argparse.ArgumentParser(
        description=f"财付通注册信息提取合并工具 v{VERSION} — 遍历 TenpayRegInfo.txt 并合并输出 xlsx · {AUTHOR}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python app_reg.py -s ../src_ref/财付通20260421 -o ./output
  python app_reg.py -s D:/data/reg_info -o D:/result -n 注册信息汇总.xlsx
        """,
    )
    parser.add_argument(
        "-s", "--source",
        required=True,
        help="数据源文件夹路径（包含 TenpayRegInfo.txt 文件的目录树）",
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="输出文件夹路径",
    )
    parser.add_argument(
        "-n", "--name",
        default="TenpayRegInfo_merge.xlsx",
        help="输出 Excel 文件名（默认: TenpayRegInfo_merge.xlsx）",
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
    logger.info(f"财付通注册信息提取合并工具 v{VERSION}")
    logger.info(f"制作人: {AUTHOR}")
    logger.info(f"数据源: {args.source}")
    logger.info(f"输出: {os.path.join(args.output, args.name)}")
    logger.info("=" * 60)

    start_time = time.time()

    # 1. 扫描文件
    files = _find_reg_files(args.source)
    logger.info(f"扫描到 {len(files)} 个 TenpayRegInfo.txt 文件")

    if not files:
        logger.warning("未找到 TenpayRegInfo.txt 文件，退出")
        print("⚠️  未找到任何 TenpayRegInfo.txt 文件")
        sys.exit(0)

    # 2. 解析文件
    success = 0
    fail = 0
    skipped = 0
    records = []

    for i, filepath in enumerate(files, 1):
        # 计算相对路径用于显示
        try:
            rel_path = os.path.relpath(filepath, args.source)
        except ValueError:
            rel_path = filepath

        try:
            result = read_tenpay_reg_info(filepath)
            if result is None:
                skipped += 1
                logger.warning(f"[{i}/{len(files)}] 跳过: {rel_path}")
            else:
                records.append(result)
                success += 1
                status = result["primary"].get("账户状态", "?")
                name = result["primary"].get("注册姓名", "?")
                account = result["primary"].get("账号", "?")
                changes = len(result.get("changes", []))
                logger.info(
                    f"[{i}/{len(files)}] {status}\t{account}\t{name}"
                    + (f"\t变更={changes}" if changes else "")
                )
        except Exception as e:
            fail += 1
            logger.error(f"[{i}/{len(files)}] 失败: {rel_path} — {e}")

    # 3. 清洗合并
    basic_df, changes_df = process_reg_data(records)

    # 3.5 提取人员基础信息（去重）
    person_df = build_person_info(basic_df)

    # 4. 输出 Excel
    output_path = os.path.join(args.output, args.name)
    result_path = write_reg_excel(basic_df, changes_df, output_path, person_df=person_df)

    elapsed = time.time() - start_time

    # 5. 打印摘要
    print()
    print("=" * 60)
    print("处理完成!")
    print(f"  文件总数: {len(files)}")
    print(f"  成功: {success}")
    print(f"  失败: {fail}")
    print(f"  跳过: {skipped}")
    print(f"  注册信息汇总: {len(basic_df)} 条")
    print(f"  变更记录: {len(changes_df)} 条")
    print(f"  基础信息(自然人): {len(person_df)} 人")
    if result_path:
        print(f"  输出文件: {result_path}")
    print(f"  耗时: {elapsed:.1f} 秒")
    print("=" * 60)

    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
