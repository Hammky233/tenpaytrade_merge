"""
数据清洗模块

职责链（按调用顺序）：
  clean_columns(df)              → 列名清洗（BOM、特殊Unicode字符）
  merge_duplicate_columns(df)    → 合并重复列（向量化实现）
  convert_amounts(df)            → 自动识别"金额(分)"列，转为"金额(元)"
  split_datetime(df)             → 拆分"交易时间"列 → 日期 + 时间（插在"交易用途类型"后面）
  calc_income_expense(df)        → 根据借贷类型拆分进账金额/出账金额
  classify_time_period(df)       → 时段分类（凌晨/早上/下午/晚上）
  classify_date_type(df)         → 日期分类（工作日/节假日/周末）
"""

import os
import json
import logging
import re
import pandas as pd
import numpy as np

logger = logging.getLogger("TenpayMerge")


# ============================================================================
# 列名工具函数
# ============================================================================

def find_column(columns, keywords):
    """
    精准匹配列名：必须同时包含所有关键词。
    用于自适应识别腾讯返回的不固定列名。

    Args:
        columns: 列名列表（pd.Index 或 list）
        keywords: 关键词列表，所有关键词必须同时出现在列名中

    Returns:
        匹配到的列名（str）或 None
    """
    for col in columns:
        col_str = str(col)
        if all(k in col_str for k in keywords):
            return col_str
    return None


def find_columns_containing(columns, keywords):
    """
    查找所有包含指定关键词组合的列。
    用于查找多个金额列等场景。

    Args:
        columns: 列名列表
        keywords: 关键词列表，所有关键词必须同时出现在列名中

    Returns:
        匹配到的列名列表
    """
    result = []
    for col in columns:
        col_str = str(col)
        if all(k in col_str for k in keywords):
            result.append(col_str)
    return result


# ============================================================================
# 清洗函数
# ============================================================================

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    清洗列名：去除 BOM 和特殊 Unicode 控制字符，去除首尾空格。

    Args:
        df: 输入 DataFrame

    Returns:
        清洗后的 DataFrame（原地修改列名）
    """
    df.columns = df.columns.astype(str)
    df.columns = df.columns.str.strip()

    # 移除常见特殊字符
    special_chars = ['﻿', '‎', '‪', '‬', '‌', '​', '‍']
    for char in special_chars:
        df.columns = df.columns.str.replace(char, '', regex=False)

    return df


def merge_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    合并重复列：当存在同名多列时，用后续列的非空值填充第一列，再删除重复列。

    向量化实现：用 combine_first 替代逐行遍历

    Args:
        df: 输入 DataFrame

    Returns:
        处理后无重复列的 DataFrame
    """
    dup_mask = df.columns.duplicated()
    if not dup_mask.any():
        return df

    dup_names = df.columns[dup_mask].unique().tolist()
    logger.info(f"发现重复列名: {dup_names}")

    for col_name in dup_names:
        col_indices = [i for i, c in enumerate(df.columns) if c == col_name]
        if len(col_indices) < 2:
            continue

        first_idx = col_indices[0]
        # 将后续重复列的非空值合并到第一列
        for dup_idx in col_indices[1:]:
            # 用第一列的 NaN/空字符串 位置，从重复列取值填充
            first_col = df.iloc[:, first_idx]
            dup_col = df.iloc[:, dup_idx]
            # 判断第一列"空"的标准：NaN 或 空字符串
            mask_empty = first_col.isna() | (first_col == '')
            # 向量化填充
            df.iloc[mask_empty.values, first_idx] = dup_col[mask_empty].values

    # 删除重复列（保留第一个出现的）
    df = df.loc[:, ~df.columns.duplicated(keep='first')]
    logger.debug(f"合并重复列后列数: {len(df.columns)}")

    return df


def convert_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """
    自动识别所有"金额(分)"列，转换为"金额(元)"并重命名。

    同时处理不包含"(分)"但包含"金额"且列名不含"(元)"的列（如"账户余额(分)"）。

    Args:
        df: 输入 DataFrame

    Returns:
        金额转换后的 DataFrame
    """
    # 查找所有包含"分"的金额列
    amount_cols_cents = find_columns_containing(df.columns, ['金额', '分'])

    rename_map = {}

    for col in amount_cols_cents:
        if col not in df.columns:
            continue
        try:
            # 先清理数据中的特殊字符（备注列可能混入的）
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].str.replace(r'[‌‎‪‬​‍﻿]', '', regex=True)
            # 转数值并除以100
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0) / 100
            new_name = col.replace('(分)', '(元)')
            rename_map[col] = new_name
            logger.debug(f"金额转换: {col} -> {new_name}")
        except Exception as e:
            logger.warning(f"金额转换失败 [{col}]: {e}")

    # 检查是否有余额相关列（可能不含"分"）
    col_balance = find_column(df.columns, ['余额'])
    if col_balance and col_balance not in rename_map:
        try:
            df[col_balance] = df[col_balance].astype(str).str.strip()
            df[col_balance] = df[col_balance].str.replace(r'[‌‎‪‬​‍﻿]', '', regex=True)
            df[col_balance] = pd.to_numeric(df[col_balance], errors='coerce').fillna(0) / 100
            if '(分)' in col_balance:
                new_name = col_balance.replace('(分)', '(元)')
            elif '(元)' not in col_balance:
                new_name = col_balance + '(元)'
            else:
                new_name = col_balance
            rename_map[col_balance] = new_name
            logger.debug(f"余额转换: {col_balance} -> {new_name}")
        except Exception as e:
            logger.warning(f"余额转换失败 [{col_balance}]: {e}")

    if rename_map:
        df.rename(columns=rename_map, inplace=True)

    return df


def split_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """
    拆分"交易时间"列 → "日期" + "时间"

    - 用 find_column 自适应识别"交易时间"列
    - 用 find_column 找到"交易用途类型"作为锚点，将拆分结果插入其后

    Args:
        df: 输入 DataFrame

    Returns:
        拆分后的 DataFrame
    """
    col_time = find_column(df.columns, ['交易', '时间'])
    if not col_time:
        logger.warning("未找到「交易时间」列，跳过时间拆分")
        return df

    # 解析时间字符串
    time_str = df[col_time].astype(str).str.strip()
    # 移除可能混入的特殊字符
    time_str = time_str.str.replace(r'[‌‎‪‬﻿]', '', regex=True)

    split_parts = time_str.str.split(n=1, expand=True)

    date_part = split_parts[0].str.strip() if split_parts.shape[1] >= 1 else time_str
    time_part = ''
    if split_parts.shape[1] > 1:
        time_part = split_parts[1].str.strip()

    # 尝试格式化日期（月/日不补零，如 2026/4/2）
    try:
        def _fmt_date(dt):
            """将 Timestamp 格式化为 年/月/日（无前导零）"""
            if pd.isna(dt):
                return dt
            return f"{dt.year}/{dt.month}/{dt.day}"

        date_parsed = pd.to_datetime(date_part, errors='coerce')
        date_formatted = date_parsed.apply(_fmt_date)
        date_formatted = date_formatted.fillna(date_part)
    except Exception:
        date_formatted = date_part

    # 删除原"交易时间"列
    df.drop(columns=[col_time], inplace=True)

    # 找到锚点列"交易用途类型"，将日期/时间插入其后
    col_purpose = find_column(df.columns, ['交易', '用途', '类型'])

    if col_purpose:
        insert_pos = df.columns.get_loc(col_purpose) + 1
    else:
        # fallback：插到交易业务类型后面
        col_biz_type = find_column(df.columns, ['交易', '业务', '类型'])
        if col_biz_type:
            insert_pos = df.columns.get_loc(col_biz_type) + 1
        else:
            insert_pos = 0  # 最后兜底：插到最前面

    # 列重排：在 insert_pos 处插入 日期、时间
    cols = df.columns.tolist()
    new_cols = cols[:insert_pos] + ['日期', '时间'] + cols[insert_pos:]
    # 赋值新列
    df['日期'] = date_formatted
    df['时间'] = time_part
    df = df[new_cols]

    logger.debug(f"时间拆分完成，日期/时间插入在位置 {insert_pos}")
    return df


def calc_income_expense(df: pd.DataFrame) -> pd.DataFrame:
    """
    根据"借贷类型"列拆分进账金额和出账金额。

    - 用 find_column 自适应识别"借贷类型"和"交易金额(元)"列
    - 进账：借贷类型包含「入」→ 进账金额 = 交易金额
    - 出账：借贷类型包含「出」→ 出账金额 = 交易金额
    - 新列追加到末尾

    Args:
        df: 输入 DataFrame

    Returns:
        添加了进账金额/出账金额的 DataFrame
    """
    col_type = find_column(df.columns, ['借贷'])
    if not col_type:
        logger.warning("未找到「借贷类型」列，跳过进账/出账拆分")
        return df

    # 查找交易金额列（已经是元）
    col_amount = find_column(df.columns, ['交易', '金额', '元'])
    if not col_amount:
        # fallback: 尝试找包含"交易金额"的列
        col_amount = find_column(df.columns, ['交易', '金额'])
    if not col_amount:
        logger.warning("未找到「交易金额(元)」列，跳过进账/出账拆分")
        return df

    type_str = df[col_type].astype(str)
    amount_numeric = pd.to_numeric(df[col_amount], errors='coerce').fillna(0)

    df['进账金额'] = 0.0
    df['出账金额'] = 0.0

    is_income = type_str.str.contains('入', na=False)
    is_expense = type_str.str.contains('出', na=False)

    df.loc[is_income, '进账金额'] = amount_numeric[is_income]
    df.loc[is_expense, '出账金额'] = amount_numeric[is_expense]

    # 将进账金额/出账金额插入到交易金额(元)列紧左边
    if col_amount and col_amount in df.columns:
        cols = [c for c in df.columns if c not in ('进账金额', '出账金额')]
        insert_pos = cols.index(col_amount)
        cols = cols[:insert_pos] + ['进账金额', '出账金额'] + cols[insert_pos:]
        df = df[cols]

    logger.debug("进账/出账金额拆分完成")
    return df


# ============================================================================
# 时段分类
# ============================================================================

def load_time_period_config(config_path: str | None = None) -> dict:
    """
    加载时段配置文件。

    Args:
        config_path: 配置文件路径，默认 scripts/config/time_period_config.json

    Returns:
        配置字典，包含"时段"列表
    """
    if config_path is None:
        from utils.paths import get_config_dir
        config_path = os.path.join(get_config_dir(), "time_period_config.json")

    if not os.path.exists(config_path):
        logger.warning(f"时段配置不存在: {config_path}，使用默认配置")
        return {
            "时段": [
                {"name": "凌晨", "start": "00:00", "end": "06:00"},
                {"name": "早上", "start": "06:00", "end": "12:00"},
                {"name": "下午", "start": "12:00", "end": "19:00"},
                {"name": "晚上", "start": "19:00", "end": "24:00"},
            ],
        }

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    logger.debug(f"时段配置已加载: {config_path}")
    return config


def _time_to_minutes(time_str: str) -> int:
    """
    将时间字符串 (HH:MM 或 HH:MM:SS) 转为分钟数。

    Args:
        time_str: 时间字符串

    Returns:
        分钟数 (0~1439)，解析失败返回 -1
    """
    if pd.isna(time_str) or not isinstance(time_str, str):
        return -1
    try:
        # 归一化冒号：全角冒号（中文输入法）→ 半角冒号
        cleaned = str(time_str).strip().replace('：', ':')
        parts = cleaned.split(':')
        if len(parts) < 2:
            return -1
        h, m = int(parts[0]), int(parts[1])
        return h * 60 + m
    except (ValueError, IndexError):
        return -1


def classify_time_period(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    """
    根据"时间"列将交易分类到对应时段，新增"时段"列在最右侧。

    匹配规则：
    - 遍历 config["时段"] 数组，按顺序匹配
    - start ≤ 分钟数 < end 则命中（start 包含，end 不包含）
    - 未命中任何时段 → "未知"
    - 时间列不存在或已存在"时段"列 → 跳过

    Args:
        df: 输入 DataFrame
        config: 时段配置字典，None 时自动加载

    Returns:
        添加了"时段"列的 DataFrame
    """
    # 幂等：已有时段列则跳过
    if "时段" in df.columns:
        logger.debug("「时段」列已存在，跳过分类")
        return df

    col_time = find_column(df.columns, ['时间'])
    if not col_time:
        logger.warning("未找到「时间」列，跳过时段分类")
        return df

    if config is None:
        config = load_time_period_config()

    periods = config.get("时段", [])
    if not periods:
        logger.warning("时段配置为空，跳过分类")
        return df

    # 预计算每个时段的分钟范围
    period_ranges = []
    for p in periods:
        start_min = _time_to_minutes(p.get("start", ""))
        end_min = _time_to_minutes(p.get("end", ""))
        # 处理 24:00 → 1440 分钟，用于 < 比较
        if p.get("end", "") == "24:00":
            end_min = 1440
        period_ranges.append((p.get("name", "未知"), start_min, end_min))

    def _classify(time_val):
        """对单个时间值进行分类"""
        minutes = _time_to_minutes(time_val)
        if minutes < 0:
            return "未知"
        for name, start_min, end_min in period_ranges:
            if start_min >= 0 and end_min >= 0:
                if start_min <= minutes < end_min:
                    return name
        return "未知"

    df = df.copy()
    df['时段'] = df[col_time].apply(_classify)

    # 统计各类别数量
    counts = df['时段'].value_counts().to_dict()
    logger.info(f"时段分类完成: {counts}")

    return df


# ============================================================================
# 日期分类（工作日 / 节假日）
# ============================================================================

# chinesecalendar 节日名称英→中映射（该库仅返回英文名称）
_HOLIDAY_NAME_MAP = {
    "New Year's Day": "元旦",
    "Spring Festival": "春节",
    "Tomb-sweeping Day": "清明节",
    "Labour Day": "劳动节",
    "Dragon Boat Festival": "端午节",
    "Mid-autumn Festival": "中秋节",
    "National Day": "国庆节",
}


def classify_date_type(df: pd.DataFrame) -> pd.DataFrame:
    """
    根据"日期"列分类为工作日/节假日/周末，新增"日期分类"列在"时段"右侧。

    节假日判断依赖 chinesecalendar 库；未安装或解析失败返回"未知"。

    ⚡ 性能：对唯一日期做缓存（365个/年），再 map 到全量行，不逐行调用 API。

    Args:
        df: 输入 DataFrame

    Returns:
        添加了"日期分类"列的 DataFrame
    """
    # 幂等：已有"日期分类"列则跳过
    if "日期分类" in df.columns:
        logger.debug("「日期分类」列已存在，跳过分类")
        return df

    col_date = find_column(df.columns, ['日期'])
    if not col_date:
        logger.warning("未找到「日期」列，跳过日期分类")
        return df

    # 尝试导入 chinesecalendar
    try:
        from chinese_calendar import is_holiday, is_workday, get_holiday_detail
    except ImportError:
        logger.warning("chinesecalendar 未安装，日期分类全部标记为「未知」")
        df = df.copy()
        df['日期分类'] = '未知'
        return df

    # 提取唯一日期（去空），为每个建立映射缓存
    date_series = df[col_date].dropna().unique()
    cache = {}

    for date_val in date_series:
        try:
            dt = pd.to_datetime(str(date_val), errors='coerce')
            if pd.isna(dt):
                cache[date_val] = '未知'
                continue

            is_hol, eng_name = get_holiday_detail(dt.date())
            if is_hol and eng_name:
                # 有名假期 → 节假日（春节）
                cn_name = _HOLIDAY_NAME_MAP.get(eng_name, eng_name)
                cache[date_val] = f'节假日（{cn_name}）'
            elif is_workday(dt.date()):
                # 工作日（含调休上班的周末）
                cache[date_val] = '工作日'
            else:
                # 普通周末 或 无名假期
                cache[date_val] = '周末'
        except Exception:
            cache[date_val] = '未知'

    # 向量化映射到全量行
    df = df.copy()
    df['日期分类'] = df[col_date].map(cache).fillna('未知')

    # 统计
    counts = df['日期分类'].value_counts().to_dict()
    logger.info(f"日期分类完成: {counts}")

    return df


# ============================================================================
# 主处理入口
# ============================================================================

def process_dataframe(df: pd.DataFrame) -> pd.DataFrame | None:
    """
    对单个 DataFrame 执行完整清洗流水线。

    流程：列名清洗→合并重复列→金额分转元→时间拆分→进账/出账拆分→时段分类→日期分类

    Args:
        df: 原始 DataFrame

    Returns:
        清洗后的 DataFrame 或 None（关键字段缺失时）
    """
    try:
        # 创建独立副本，避免 SettingWithCopyWarning
        df = df.copy()

        # 1. 列名清洗
        df = clean_columns(df)

        # 2. 合并重复列
        df = merge_duplicate_columns(df)

        # 3. 关键字段验证
        col_time = find_column(df.columns, ['交易', '时间'])
        col_amount = find_column(df.columns, ['交易', '金额'])
        col_type = find_column(df.columns, ['借贷'])

        if not col_time or not col_amount or not col_type:
            logger.warning(
                f"关键字段缺失 - 时间:{col_time}, 金额:{col_amount}, 借贷类型:{col_type}"
            )
            logger.warning(f"  当前列: {list(df.columns)}")
            return None

        # 4. 金额转换（分→元）
        df = convert_amounts(df)

        # 5. 时间拆分
        df = split_datetime(df)

        # 6. 进账/出账拆分
        df = calc_income_expense(df)

        # 7. 时段分类（根据"时间"列归入凌晨/早上/下午/晚上等）
        df = classify_time_period(df)

        # 8. 日期分类（根据"日期"列区分工作日/节假日/周末）
        df = classify_date_type(df)

        return df

    except Exception as e:
        import traceback
        logger.error(f"数据处理异常: {e}")
        logger.debug(traceback.format_exc())
        return None
