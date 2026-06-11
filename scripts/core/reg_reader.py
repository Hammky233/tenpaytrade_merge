"""
注册信息文件读取模块（TenpayRegInfo.txt）

解析财付通注册信息文件，支持两种区域格式：
- 区域一：基本信息表（含主记录行 + 可选银行卡扩展行）
- 区域二：注销/变更信息表

数据格式：UTF-8 / Tab 分隔
"""

import os
import re
import logging

logger = logging.getLogger("TenpayMerge")

# 基本信息表预期的列名（用于验证）
BASIC_HEADER_KEYWORDS = ['账户状态', '账号', '注册姓名', '注册时间', '注册身份证号']

# 变更信息表预期的列名
CHANGE_HEADER_KEYWORDS = ['注销时间']

# 银行卡扩展行判断：前6列为空的即为银行卡扩展行
BANK_CARD_EMPTY_COLS = 6  # 账户状态~绑定手机 这6列在银行卡行中为空


def _detect_encoding_and_read(filepath: str) -> list[str] | None:
    """
    自动检测编码并读取文件所有行。
    策略：UTF-8 → GBK → GB2312 → UTF-16
    """
    for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-16']:
        try:
            with open(filepath, 'r', encoding=encoding, errors='replace') as f:
                return f.readlines()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def _try_parse_not_found(lines: list[str], filepath: str) -> dict | None:
    """
    尝试解析"账号不存在"格式的文件。

    格式示例：
        账号oe15nt_qgifd5pxpkrousisx1drw@aa.tenpay.com不存在
        账号A119999999000不存在

    Returns:
        解析结果 dict 或 None（不是此格式时）
    """
    if len(lines) != 1:
        return None

    line = lines[0].strip()
    # 匹配 "账号XXX不存在"
    if '账号' not in line or '不存在' not in line:
        return None

    # 提取账号（"账号"和"不存在"之间的内容）
    import re
    match = re.search(r'账号(.+?)不存在', line)
    if not match:
        return None

    account = match.group(1).strip()

    result = {
        "primary": {
            "账户状态": "账号不存在",
            "账号": account,
            "注册姓名": "",
            "注册时间": "",
            "注册身份证号": "",
            "绑定手机": "",
            "绑定状态": "",
            "开户行信息": "",
            "银行账号": "",
        },
        "bank_cards": [],
        "changes": [],
        "source_file": filepath,
        "case_number": _extract_case_number(filepath),
    }
    logger.debug(f"账号不存在: {account}")
    return result


def _extract_case_number(filepath: str) -> str:
    """
    从文件路径中提取调证编号。
    例如：...深宝监调证[2026]19038号... → "19038号"
    """
    match = re.search(r'调证\[[^\]]*\](\d+号)', filepath)
    if match:
        return match.group(1)
    return ""


def _parse_basic_section(lines: list[str]) -> dict:
    """
    解析基本信息表区域。
    返回 {"header": [...], "primary": [...], "bank_cards": [[...], ...]}
    """
    result = {"header": [], "primary": [], "bank_cards": []}

    if not lines:
        return result

    # 第一行为表头
    header_line = lines[0].strip()
    if header_line:
        result["header"] = [col.strip() for col in header_line.split('\t')]

    expected_cols = len(result["header"])

    # 解析数据行
    for i in range(1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue

        parts = line.split('\t')

        # 补齐或截断列
        if len(parts) > expected_cols:
            # 多余列合并到最后一列（遵循 reader.py 的约定）
            extra = '\t'.join(parts[expected_cols - 1:])
            parts = parts[:expected_cols - 1] + [extra]
        elif len(parts) < expected_cols:
            parts.extend([''] * (expected_cols - len(parts)))

        # 判断是主记录行还是银行卡扩展行
        # 前 BANK_CARD_EMPTY_COLS 列全为空 → 银行卡扩展行
        first_n = [p.strip() for p in parts[:BANK_CARD_EMPTY_COLS]]
        if all(p == '' for p in first_n):
            result["bank_cards"].append(parts)
        else:
            # 主记录行（一个文件应该只有一行，但以防万一）
            if not result["primary"]:
                result["primary"] = parts
            else:
                # 额外的非银行卡行也存为主记录（边缘情况）
                logger.debug(f"发现多余主记录行，已忽略")

    return result


def _parse_change_section(lines: list[str]) -> dict:
    """
    解析注销/变更信息表区域。
    返回 {"header": [...], "records": [[...], ...]}
    """
    result = {"header": [], "records": []}

    if not lines:
        return result

    # 跳过可能的空行，找到表头
    header_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped:
            header_idx = i
            break

    if header_idx < 0:
        return result

    header_line = lines[header_idx].strip()
    result["header"] = [col.strip() for col in header_line.split('\t')]
    expected_cols = len(result["header"])

    # 解析数据行
    for i in range(header_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue

        parts = line.split('\t')

        # 跳过全部为空的"分隔行"（如单独的空tab行）
        if all(p.strip() == '' for p in parts):
            continue

        if len(parts) > expected_cols:
            extra = '\t'.join(parts[expected_cols - 1:])
            parts = parts[:expected_cols - 1] + [extra]
        elif len(parts) < expected_cols:
            parts.extend([''] * (expected_cols - len(parts)))

        # 跳过完全为空的行
        if any(p.strip() != '' for p in parts):
            result["records"].append(parts)

    return result


def read_tenpay_reg_info(filepath: str) -> dict | None:
    """
    读取单个 TenpayRegInfo.txt 文件，提取注册信息。

    Args:
        filepath: txt 文件路径

    Returns:
        dict:
            {
                "primary": dict,       # 主记录 {列名: 值}
                "bank_cards": list,    # 银行卡记录列表 [{列名: 值}, ...]
                "changes": list,       # 变更/注销记录列表 [{列名: 值}, ...]
                "source_file": str,    # 源文件相对路径（相对于 source 目录）
                "case_number": str,    # 调证编号
            }
        或 None（文件无法读取/无有效数据时）
    """
    # 预检查：文件大小
    try:
        size = os.path.getsize(filepath)
        if size < 20:  # 极小文件视为空
            logger.info(f"跳过空文件（{size}B）: ...{os.path.sep}{os.path.basename(os.path.dirname(filepath))}{os.path.sep}{os.path.basename(filepath)}")
            return None
    except OSError:
        pass

    # 读取文件
    lines = _detect_encoding_and_read(filepath)
    if lines is None:
        logger.error(f"无法识别编码: {filepath}")
        return None

    if not lines:
        logger.warning(f"文件为空: {filepath}")
        return None

    # 预处理：去除 BOM
    cleaned_lines = []
    for line in lines:
        # 去除 UTF-8 BOM
        if line.startswith('﻿'):
            line = line[1:]
        cleaned_lines.append(line)

    # 尝试"账号不存在"格式（单行特殊格式）
    not_found_result = _try_parse_not_found(cleaned_lines, filepath)
    if not_found_result is not None:
        return not_found_result

    # 清掉末尾的空行，避免循环误判
    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()

    if not cleaned_lines:
        logger.warning(f"文件无有效内容: {filepath}")
        return None

    # 找到"注销信息"分隔标记
    split_idx = -1
    for i, line in enumerate(cleaned_lines):
        stripped = line.strip()
        # 匹配"注销信息"（可能前后有空格）
        if stripped == '注销信息' or stripped.startswith('注销信息'):
            split_idx = i
            break

    # 分割两个区域
    if split_idx >= 0:
        basic_lines = cleaned_lines[:split_idx]
        # 跳过"注销信息"标题行本身
        change_lines = cleaned_lines[split_idx + 1:]
    else:
        # 没有分隔标记，整个文件就是基本信息表
        basic_lines = cleaned_lines
        change_lines = []

    # 清理基本区域末尾的空行
    while basic_lines and not basic_lines[-1].strip():
        basic_lines.pop()

    # 解析基本区域
    basic_data = _parse_basic_section(basic_lines)

    if not basic_data["header"]:
        logger.warning(f"基本信息表表头为空: {filepath}")
        return None

    if not basic_data["primary"]:
        logger.warning(f"无主记录行: {filepath}")
        return None

    # 构建主记录字典
    header = basic_data["header"]
    primary = dict(zip(header, basic_data["primary"]))

    # 检查主记录中"账号"是否为空
    account = primary.get('账号', '').strip()
    if not account:
        logger.warning(f"账号为空，跳过: {filepath}")
        return None

    # 构建银行卡字典列表
    bank_cards = []
    for row in basic_data["bank_cards"]:
        card_dict = dict(zip(header, row))
        # 只保留有银行卡号的行
        if card_dict.get('银行账号', '').strip():
            bank_cards.append(card_dict)

    # 解析变更区域
    change_data = _parse_change_section(change_lines)
    changes = []
    for row in change_data["records"]:
        change_dict = dict(zip(change_data["header"], row))
        # 只保留有账号的行
        if change_dict.get('账号', '').strip():
            changes.append(change_dict)

    # 提取调证编号
    case_number = _extract_case_number(filepath)

    result = {
        "primary": primary,
        "bank_cards": bank_cards,
        "changes": changes,
        "source_file": filepath,
        "case_number": case_number,
    }

    logger.debug(
        f"读取注册信息: 账号={primary.get('账号', '?')}, "
        f"状态={primary.get('账户状态', '?')}, "
        f"银行卡={len(bank_cards)}, 变更={len(changes)}"
    )

    return result
