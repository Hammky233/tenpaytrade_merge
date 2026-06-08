import os
import pandas as pd
import tkinter as tk
from tkinter import filedialog
import warnings

warnings.filterwarnings('ignore')


# =========================
# 文件选择
# =========================
def select_folder(title):
    root = tk.Tk()
    root.withdraw()
    return filedialog.askdirectory(title=title)


# =========================
# 查找文件
# =========================
def find_files(folder):
    result = []
    for root_dir, dirs, files in os.walk(folder):
        for f in files:
            if f == "TenpayTrades.txt":
                result.append(os.path.join(root_dir, f))
    return result


# =========================
# 列名清洗和去重
# =========================
def clean_columns(df):
    """
    清洗列名：去除特殊字符、处理重复列名
    """
    # 转换为字符串并去除首尾空格
    df.columns = df.columns.astype(str)
    df.columns = df.columns.str.strip()

    # 清理特殊字符
    df.columns = df.columns.str.replace('\ufeff', '', regex=False)
    df.columns = df.columns.str.replace('\u200e', '', regex=False)
    df.columns = df.columns.str.replace('\u202a', '', regex=False)

    return df


# =========================
# 合并重复列（修复版）
# =========================
def merge_duplicate_columns(df):
    """
    合并同名列：
    - 优先保留非空值
    - 删除重复的空列
    """
    # 获取所有列名
    cols = df.columns.tolist()

    # 找出重复的列名
    dup_cols = df.columns[df.columns.duplicated()].unique().tolist()

    if not dup_cols:
        return df

    print(f"⚠️ 发现重复列名: {dup_cols}")

    for col_name in dup_cols:
        # 获取该列名出现的所有位置索引
        col_indices = [i for i, c in enumerate(cols) if c == col_name]

        if len(col_indices) > 1:
            # 保留第一列，用后面列的非空值填充第一列
            first_idx = col_indices[0]

            for dup_idx in col_indices[1:]:
                # 找出当前列不为空的行
                mask = df.iloc[:, dup_idx].notna() & (df.iloc[:, dup_idx] != '')
                # 用非空值更新第一列（按行遍历）
                for row_idx in df.index[mask]:
                    df.iloc[row_idx, first_idx] = df.iloc[row_idx, dup_idx]

    # 删除重复列（保留第一个出现的）
    df = df.loc[:, ~df.columns.duplicated(keep='first')]

    print(f"✔ 已合并重复列，当前列数: {len(df.columns)}")

    return df


# =========================
# 模糊匹配列（必须同时包含所有关键词）
# =========================
def find_column(columns, keywords):
    """
    精准匹配列名，必须同时包含所有关键词
    """
    for col in columns:
        if all(k in col for k in keywords):
            return col
    return None


# =========================
# 查找所有包含指定关键词的列（用于查找多个金额列）
# =========================
def find_amount_columns(columns):
    """
    查找所有需要转换金额的列（包含"金额"和"分"的列）
    返回：需要处理的列名列表
    """
    amount_cols = []
    for col in columns:
        if '金额' in col and '分' in col:
            amount_cols.append(col)
    return amount_cols


# =========================
# 数据处理
# =========================
def process_df(df):
    try:
        # 先清洗列名
        df = clean_columns(df)

        # 处理重复列
        df = merge_duplicate_columns(df)

        # 创建副本
        df = df.copy()
        cols = df.columns.tolist()

        print("当前列名:", cols)

        # ===== 字段识别 =====
        col_time = find_column(cols, ['交易', '时间'])
        col_amount = find_column(cols, ['交易', '金额'])
        col_balance = find_column(cols, ['余额'])
        col_type = find_column(cols, ['借贷'])

        # 查找所有包含"金额(分)"的列
        amount_columns = find_amount_columns(cols)
        print(f"发现需要转换的金额列: {amount_columns}")

        if not col_time or not col_amount or not col_type:
            print("⚠️ 字段识别失败:")
            print(f"  时间列: {col_time}")
            print(f"  金额列: {col_amount}")
            print(f"  类型列: {col_type}")
            print(f"  所有列: {cols}")
            return None

        print(f"识别字段 - 时间:{col_time}, 金额:{col_amount}, 余额:{col_balance}, 类型:{col_type}")

        # =========================
        # 金额处理（分转元）- 处理所有金额列
        # =========================
        rename_map = {}

        for amount_col in amount_columns:
            if amount_col in df.columns:
                # 转换为数值并除以100
                df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce').fillna(0) / 100
                # 重命名：将"(分)"替换为"(元)"
                new_name = amount_col.replace('(分)', '(元)')
                rename_map[amount_col] = new_name
                print(f"✔ 已转换: {amount_col} -> {new_name}")

        # 如果余额列存在但没有被上面的循环处理（列名不包含"分"的情况）
        if col_balance and col_balance in df.columns and col_balance not in rename_map:
            df[col_balance] = pd.to_numeric(df[col_balance], errors='coerce').fillna(0) / 100
            if '(分)' in col_balance:
                new_name = col_balance.replace('(分)', '(元)')
            else:
                new_name = col_balance + '(元)'
            rename_map[col_balance] = new_name
            print(f"✔ 已转换余额: {col_balance} -> {new_name}")

        # 执行重命名
        df.rename(columns=rename_map, inplace=True)

        # 获取重命名后的交易金额列名
        col_amount_new = rename_map.get(col_amount, col_amount)

        # =========================
        # 时间拆分
        # =========================
        time_col_idx = df.columns.get_loc(col_time)

        time_str = df[col_time].astype(str).str.strip()
        split_parts = time_str.str.split(n=1, expand=True)

        date_part = split_parts[0].str.strip()
        time_part = ''
        if split_parts.shape[1] > 1:
            time_part = split_parts[1].str.strip()

        df['日期'] = pd.to_datetime(date_part, errors='coerce').dt.strftime('%Y/%m/%d')
        df['日期'] = df['日期'].fillna(date_part)
        df['时间'] = time_part

        df.drop(columns=[col_time], inplace=True)

        all_cols = df.columns.tolist()
        all_cols.remove('日期')
        all_cols.remove('时间')

        new_cols = all_cols[:time_col_idx] + ['日期', '时间'] + all_cols[time_col_idx:]
        df = df[new_cols]

        # =========================
        # 进账/出账金额
        # =========================
        amount_idx = df.columns.get_loc(col_amount_new)

        df['进账金额'] = 0.0
        df['出账金额'] = 0.0

        type_str = df[col_type].astype(str)
        is_income = type_str.str.contains('入', na=False)
        is_expense = type_str.str.contains('出', na=False)

        df.loc[is_income, '进账金额'] = df.loc[is_income, col_amount_new]
        df.loc[is_expense, '出账金额'] = df.loc[is_expense, col_amount_new]

        all_cols = df.columns.tolist()
        all_cols.remove('进账金额')
        all_cols.remove('出账金额')

        new_cols = all_cols[:amount_idx] + ['进账金额', '出账金额'] + all_cols[amount_idx:]
        df = df[new_cols]

        return df

    except Exception as e:
        import traceback
        print("❌ process_df失败:", e)
        traceback.print_exc()
        return None


# =========================
# 安全读取 txt
# =========================
def safe_read_txt(file):
    try:
        with open(file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        if not lines:
            print(f"⚠️ 文件为空: {file}")
            return None

        # 解析第一行作为列名
        header = lines[0].strip().split('\t')
        # 清理列名首尾空格
        header = [col.strip() for col in header]

        expected_cols = len(header)

        data_rows = []

        for i, line in enumerate(lines[1:], 1):
            line = line.strip()
            if not line:
                continue

            parts = line.split('\t')

            # 跳过重复的列名行
            if len(parts) == len(header) and parts == header:
                continue

            # 处理列数不匹配
            if len(parts) > expected_cols:
                extra = '\t'.join(parts[expected_cols - 1:])
                parts = parts[:expected_cols - 1] + [extra]
            elif len(parts) < expected_cols:
                parts.extend([''] * (expected_cols - len(parts)))

            data_rows.append(parts)

        if not data_rows:
            print(f"⚠️ 无有效数据: {file}")
            return None

        df = pd.DataFrame(data_rows, columns=header)
        return df

    except Exception as e:
        import traceback
        print(f"❌ 读取文件失败: {file}")
        traceback.print_exc()
        return None


# =========================
# 合并多个文件
# =========================
def merge_files(file_list):
    result = []
    success_count = 0
    fail_count = 0

    for file in file_list:
        try:
            df = safe_read_txt(file)

            if df is None or df.empty:
                fail_count += 1
                continue

            print(f"\n处理: {os.path.basename(os.path.dirname(file))}/{os.path.basename(file)}")
            df = process_df(df)

            if df is not None and not df.empty:
                result.append(df)
                success_count += 1
                print(f"✔ 成功 ({len(df)} 行)")
            else:
                fail_count += 1

        except Exception as e:
            fail_count += 1
            print(f"✘ 异常: {file}")

    print(f"\n{'=' * 60}")
    print(f"处理结果: 成功 {success_count} 个, 失败 {fail_count} 个")

    if result:
        # 合并所有DataFrame
        merged_df = pd.concat(result, ignore_index=True)

        # 最终再次检查重复列
        if merged_df.columns.duplicated().any():
            dup_cols = merged_df.columns[merged_df.columns.duplicated()].unique().tolist()
            print(f"⚠️ 最终合并后仍有重复列: {dup_cols}")
            merged_df = merge_duplicate_columns(merged_df)

        return merged_df
    else:
        return pd.DataFrame()


# =========================
# 主程序
# =========================
def main():
    print("=" * 60)
    print("财付通交易流水处理工具 v3.2（自动识别所有金额列）")
    print("=" * 60)

    source = select_folder("选择数据源文件夹")
    if not source:
        print("未选择数据源")
        return

    output = select_folder("选择输出文件夹")
    if not output:
        print("未选择输出位置")
        return

    files = find_files(source)

    if not files:
        print("未找到 TenpayTrades.txt 文件")
        return

    print(f"\n找到 {len(files)} 个文件，开始处理...\n")

    df = merge_files(files)

    if df.empty:
        print("\n无有效数据可以输出")
        return

    output_path = os.path.join(output, "Tenpay_merge.xlsx")

    try:
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='财付通交易汇总')

            # 调整列宽
            worksheet = writer.sheets['财付通交易汇总']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if cell.value and len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = max(adjusted_width, 8)

        print(f"\n✅ 完成! 输出文件: {output_path}")
        print(f"📊 共处理 {len(df)} 条交易记录")
        print(f"📋 列数: {len(df.columns)}")
        print(f"📋 最终列名:")
        for i, col in enumerate(df.columns, 1):
            print(f"   {i}. {col}")
    except Exception as e:
        print(f"❌ 输出Excel失败: {e}")
        csv_path = os.path.join(output, "Tenpay_merge.csv")
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"已输出CSV备选: {csv_path}")


if __name__ == "__main__":
    main()
    