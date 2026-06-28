"""
地点提取模块 — 通过 DeepSeek 大模型从停车缴费备注中提取地点信息

功能：
  extract_locations(parking_df, api_key, ...) → 在停车缴费 DataFrame 最右侧添加/更新「地点」列

设计原则：
  - 只读「备注2」列，只写「地点」列
  - 已有非"无"的地点值不覆盖（保护人工修正）
  - 去重后并发大块调用 API，数百条去重备注 10 秒内完成
"""

import json
import logging
import re
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from utils.columns import find_column
from utils.clean_text import clean_special_chars

logger = logging.getLogger("TenpayMerge")

# ============================================================================
# 配置常量
# ============================================================================

API_URL = "https://api.deepseek.com/v1/chat/completions"

# 以下参数通过 scripts/config/location_config.json 管理，
# 文件缺失时使用 load_location_config() 中的硬编码默认值。
# 模型名（如 deepseek-chat、deepseek-reasoner）可在配置文件中修改，
# 无需改动代码。

_config_cache = None


def load_location_config(config_path: str | None = None) -> dict:
    """
    加载地点识别配置文件。

    遵循其他业务模块（parking、special_filter）的配置加载惯例。
    支持开发环境和 PyInstaller 打包环境。

    Args:
        config_path: 配置文件路径，默认 scripts/config/location_config.json

    Returns:
        配置字典，包含 model, max_workers, chunk_size, request_timeout
    """
    if config_path is not None:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    from utils.config_loader import load_json_config
    return load_json_config("location_config", {
        "model": "deepseek-v4-pro",
        "max_workers": 8,
        "chunk_size": 100,
        "request_timeout": 60,
    })


def _get_config() -> dict:
    """惰性加载配置，首次调用后缓存。"""
    global _config_cache
    if _config_cache is None:
        _config_cache = load_location_config()
    return _config_cache


SYSTEM_PROMPT = (
    "你是地点提取助手。从停车缴费备注文本中提取地点名称"
    "（小区名、商场名、停车场名、大厦名、街道名）。\n"
    "\n"
    "常见格式及提取规则：\n"
    "\n"
    "【格式1】地点在停车关键词之前，用\"-\"或空格分隔：\n"
    '  "惠州大亚湾海伦堡爱ME城市停车场-停车缴费-粤B" → "惠州大亚湾海伦堡爱ME城市停车场"\n'
    '  "壹方城-停车缴费" → "壹方城"\n'
    '  "壹方汇-停车缴费" → "壹方汇"\n'
    '  "简上商务大楼停车场-停车缴费-粤B-车道码支付" → "简上商务大楼停车场"\n'
    '  "阳光海小区停车场-粤B-临停缴费" → "阳光海小区停车场"\n'
    '  "汇福花园停车场-粤B-临停缴费" → "汇福花园停车场"\n'
    '  "深圳市青少年活动中心小区-粤B-停车费" → "深圳市青少年活动中心小区"\n'
    '  "宝珠花园停车场 - 临时车缴费 - 粤B" → "宝珠花园停车场"\n'
    '  "深圳宝安海裕停车场-粤B停车费" → "深圳宝安海裕停车场"\n'
    '  "红山6979停车场-粤B" → "红山6979停车场"\n'
    "\n"
    "【格式2】地点在停车关键词之后（\"-\"分隔，地点夹在中间或末尾）：\n"
    '  "停车费用-粤B-荔园阁停车场" → "荔园阁停车场"\n'
    '  "停车费用-卓悦汇购物中心-粤B-35元" → "卓悦汇购物中心"\n'
    '  "停车费用-卓悦中心OneAvenue-粤B-30元" → "卓悦中心OneAvenue"\n'
    "\n"
    "【格式3】地点用括号包裹 — 支持【】［］[]（）：\n"
    '  "【粤B】在【欢乐港湾滨海文化公园P6-停车场】支付停车费6.50元" → "欢乐港湾滨海文化公园P6-停车场"\n'
    '  "【粤B】在【海雅缤纷城-停车场】支付停车费5.00元" → "海雅缤纷城-停车场"\n'
    '  "【粤B】在【欢乐港湾商业东岸P1-停车场】支付停车费15.00元" → "欢乐港湾商业东岸P1-停车场"\n'
    '  "【粤B】在【大中华东方新天地-停车场】支付停车费60.00元" → "大中华东方新天地-停车场"\n'
    '  "[粤B]在[应人石]支付停车费20元" → "应人石"\n'
    '  "临停车辆缴费30.00元（粤B）" → "无"  （括号内是车牌，不是地点）\n'
    "\n"
    "【格式4】逗号分隔：地点,车牌,日期/时间：\n"
    '  "YT华海达停车场,粤B,2021-10-17 10:47:00" → "YT华海达停车场"\n'
    "\n"
    "【格式5】\"给XXX\"付款模式，地点在\"给\"之后：\n"
    '  "扫二维码付款-给御锦公馆停车场" → "御锦公馆停车场"\n'
    "\n"
    "【格式6】整个备注就是一个地点名称（无分隔符、无车牌、无停车关键词）：\n"
    '  "宝安新村停车场" → "宝安新村停车场"\n'
    '  "前海东岸花园" → "前海东岸花园"\n'
    '  "六区停车区" → "六区停车区"\n'
    "\n"
    "【格式7】无地点信息，仅金额/车牌/参考号/系统名 → 返回\"无\"：\n"
    '  "停车费用-粤-B-0000012345" → "无"\n'
    '  "停车支付5.00元(粤B)" → "无"\n'
    '  "ETCP-代扣支付-临时停车缴费" → "无"\n'
    '  "停车费用;" → "无"\n'
    '  "停车缴费-P181005640" → "无"\n'
    '  "JSPAY-粤-B-P201229324" → "无"\n'
    "\n"
    "核心原则：\n"
    "- 地点名称保留完整层级，如\"欢乐港湾商业东岸P1-停车场\"不简化为\"停车场\"\n"
    "- 不要把车牌号（粤+字母数字）、金额、日期、参考号、系统编号当作地点\n"
    "- 注意英文名也是地点的一部分，如\"YT华海达\"\"卓悦中心OneAvenue\"\n"
    "- 如果备注中完全没有地点名称，返回\"无\"\n"
    "\n"
    '无法确定的返回"无"。'
    "严格按JSON数组格式返回，不要markdown、不要解释、不要换行。"
)


# ============================================================================
# API 调用
# ============================================================================

def _call_deepseek(notes: list[str], api_key: str,
                   _urlopen=urllib.request.urlopen) -> list[str]:
    """
    调用 DeepSeek API，发送一批备注文本，返回等长地点数组。

    Args:
        notes: 待提取的备注文本列表（长度 ≤ chunk_size）
        api_key: DeepSeek API Key
        _urlopen: 可注入的 urlopen 函数（默认 urllib.request.urlopen），
                  用于测试时模拟 HTTP 响应而不发起真实网络请求

    Returns:
        等长的地点名称列表（索引一一对应）

    Raises:
        ValueError: API 返回无法解析 或 HTTP 错误
        URLError: 网络错误
    """
    if not notes:
        return []

    cfg = _get_config()
    model_name = cfg["model"]
    timeout = cfg["request_timeout"]

    # 构建请求
    user_message = (
        "为以下停车备注提取地点，返回JSON字符串数组"
        "（长度必须等于输入数组长度）：\n"
        + json.dumps(notes, ensure_ascii=False)
    )

    payload = json.dumps({
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    logger.info(f"DeepSeek API 请求: model={model_name}, notes={len(notes)} 条, "
                f"timeout={timeout}s")

    try:
        with _urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        code = e.code
        if code == 401:
            msg = ("API Key 无效或已过期，请在设置中重新填入有效的 "
                   "DeepSeek API Key")
        elif code == 402:
            msg = ("DeepSeek 账户余额不足，请前往 "
                   "https://platform.deepseek.com 充值后重试")
        elif code == 429:
            msg = "请求频率超限（429），请稍后重试"
        elif 500 <= code < 600:
            msg = f"DeepSeek 服务器暂时不可用（HTTP {code}），请稍后重试"
        else:
            msg = f"API 请求失败（HTTP {code}）"
        if error_body:
            msg += f" — {error_body[:200]}"
        raise ValueError(msg) from e

    # 解析响应 JSON
    try:
        data = json.loads(body)
        content = data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        raise ValueError(f"API 响应结构异常: {body[:500]}") from e

    # 从 LLM 回复中提取地点数组
    locations = _parse_location_response(content)

    # 诊断日志：记录 API 原始返回，方便排查解析问题
    logger.debug(
        f"API raw content (前300字): {content[:300]}"
    )
    logger.debug(
        f"解析结果: {len(locations)} 条, "
        f"识别到地点 {sum(1 for v in locations if v != '无')} 个, "
        f"前5条: {locations[:5]}"
    )

    # 长度对齐
    if len(locations) != len(notes):
        logger.warning(
            f"API 返回长度 {len(locations)} ≠ 输入长度 {len(notes)}，补齐/截断"
        )
        while len(locations) < len(notes):
            locations.append("无")
        locations = locations[:len(notes)]

    return locations


def _parse_location_response(content: str) -> list[str]:
    """
    解析 LLM 返回的内容为地点字符串列表。

    模型可能返回：
    - 纯 JSON 数组：["地点1", "地点2"]
    - Markdown 代码块包裹
    - 带编号前缀的文本
    """
    content = content.strip()

    # 尝试 1：直接解析为 JSON 数组
    try:
        result = json.loads(content)
        if isinstance(result, list):
            return [str(v) for v in result]
    except json.JSONDecodeError:
        pass

    # 尝试 2：提取最外层 [...] 片段
    start = content.find("[")
    if start >= 0:
        end = content.rfind("]")
        if end > start:
            try:
                result = json.loads(content[start:end + 1])
                if isinstance(result, list):
                    return [str(v) for v in result]
            except json.JSONDecodeError:
                pass

    # 尝试 3：按行解析（去掉可能的前导编号 "1. " "1) " "1、"）
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    cleaned = []
    for line in lines:
        line = re.sub(r'^\d+[\.\)、]\s*', '', line)
        if line:
            cleaned.append(line)

    if cleaned:
        return cleaned

    # 彻底失败
    return ["无"]


# ============================================================================
# 主入口
# ============================================================================

def extract_locations(
    parking_df: pd.DataFrame,
    api_key: str,
    existing_locations: dict | None = None,
    progress_callback=None,
) -> pd.DataFrame:
    """
    从停车缴费 DataFrame 的「备注2」列提取地点信息，写入「地点」列。

    - 已存在非"无"的地点值会被保留（保护人工修正）
    - existing_locations 映射优先级高于 LLM（多批次合并场景）

    Args:
        parking_df: 停车缴费 DataFrame
        api_key: DeepSeek API Key
        existing_locations: 可选 dict{备注2文本: 地点}，来自既往文件的地点映射
        progress_callback: 可选 callable(msg: str)，向 GUI 回传进度

    Returns:
        添加/更新了「地点」列的 DataFrame（副本）
    """
    if parking_df.empty:
        return parking_df

    df = parking_df.copy()
    t_start = time.time()

    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    # ── 1. 自适应找到「备注2」列 ──
    col_note2 = find_column(df.columns, ["备注2"])
    if not col_note2:
        _log("未找到「备注2」列，跳过地点提取")
        if "地点" not in df.columns:
            df["地点"] = "无"
        return df

    # ── 2. 初始化「地点」列，记录已有人工修正的行 ──
    if "地点" not in df.columns:
        df["地点"] = "无"

    already_set = (
        df["地点"].notna() & (df["地点"] != "无") & (df["地点"] != "")
    )
    preserved_count = already_set.sum()
    if preserved_count > 0:
        _log(f"已有 {preserved_count} 条地点信息，将保留不覆盖")

    # ── 3. 应用已有地点映射（多批次合并场景）──
    existing_applied = 0
    if existing_locations:
        for idx in df.index:
            if already_set.loc[idx]:
                continue
            note = df.at[idx, col_note2]
            if pd.notna(note) and str(note) in existing_locations:
                loc = existing_locations[str(note)]
                if loc and loc != "无":
                    df.at[idx, "地点"] = loc
                    existing_applied += 1
        if existing_applied > 0:
            _log(f"从既往数据恢复 {existing_applied} 条地点")

    # ── 4. 收集仍需提取的唯一备注2 ──
    still_empty = ~(
        (df["地点"].notna()) & (df["地点"] != "无") & (df["地点"] != "")
    )
    pending_series = df.loc[still_empty, col_note2].dropna().astype(str)
    # 清理 Unicode 控制字符
    pending_series = pending_series.apply(clean_special_chars)
    pending_series = pending_series[pending_series.str.strip() != ""]

    if pending_series.empty:
        total = (df["地点"] != "无").sum()
        _log(f"所有行均已有地点信息（共 {total} 条），无需调用 API")
        return df

    unique_notes = pending_series.unique().tolist()
    _log(f"待提取 {len(pending_series)} 行, 去重 {len(unique_notes)} 条备注文本")

    # ── 5. 并发调用 DeepSeek API ──
    location_map: dict[str, str] = {}

    cfg = _get_config()
    chunk_size = cfg["chunk_size"]
    max_workers = cfg["max_workers"]

    if len(unique_notes) <= chunk_size:
        # 单块，直接调用
        _log(f"调用 DeepSeek API ({len(unique_notes)} 条)...")
        try:
            locations = _call_deepseek(unique_notes, api_key)
            for note, loc in zip(unique_notes, locations):
                location_map[note] = loc
            recognized = sum(1 for v in locations if v != "无")
            _log(f"API 返回 {recognized}/{len(unique_notes)} 个地点")
        except Exception as e:
            _log(f"地点提取 API 调用失败: {e}")
            return df
    else:
        # 分块并发
        chunks = []
        for i in range(0, len(unique_notes), chunk_size):
            chunks.append(unique_notes[i:i + chunk_size])

        n_workers = min(max_workers, len(chunks))
        _log(f"分 {len(chunks)} 块, {n_workers} 线程并发调用 DeepSeek API...")

        errors = 0
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            future_to_chunk = {
                executor.submit(_call_deepseek, chunk, api_key): (i, chunk)
                for i, chunk in enumerate(chunks)
            }

            for future in as_completed(future_to_chunk):
                idx_chunk, chunk = future_to_chunk[future]
                try:
                    locations = future.result()
                    for note, loc in zip(chunk, locations):
                        location_map[note] = loc
                    hit = sum(1 for v in locations if v != "无")
                    _log(f"块 {idx_chunk + 1}/{len(chunks)}: {hit}/{len(chunk)} 识别到地点")
                except Exception as e:
                    errors += 1
                    _log(f"块 {idx_chunk + 1}/{len(chunks)} 失败: {e}")
                    for note in chunk:
                        location_map[note] = "无"

        if errors > 0:
            _log(f"{errors}/{len(chunks)} 块调用失败，相关行填\"无\"")

    # ── 6. 填回 DataFrame ──
    for idx in df.index:
        if still_empty.loc[idx]:
            note_val = df.at[idx, col_note2]
            if pd.notna(note_val):
                cleaned = clean_special_chars(str(note_val))
                if cleaned in location_map:
                    df.at[idx, "地点"] = location_map[cleaned]

    # ── 7. 统计 ──
    total = (df["地点"] != "无").sum()
    elapsed = time.time() - t_start

    # 采样日志：展示几个提取结果，方便人工核对
    if location_map:
        samples = [
            (k, v) for k, v in list(location_map.items())[:5]
            if v != "无"
        ]
        if samples:
            _log("📍 提取采样（备注 → 地点）:")
            for note, loc in samples:
                _log(f"   \"{note[:50]}\" → \"{loc}\"")

    _log(
        f"地点提取完成: {total}/{len(df)} 条有地点信息, "
        f"耗时 {elapsed:.1f} 秒"
    )

    return df
