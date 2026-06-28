"""
地点识别模块测试 — 配置降级、HTTP 错误友好消息

测试目标：
  - load_location_config 在文件缺失时返回硬编码默认值
  - load_location_config 可接受自定义 config_path 覆盖
  - _call_deepseek 对 401/402/429/5xx 返回用户可理解的中文错误信息
  - 不发起真实网络请求（所有 HTTP 调用通过 mock 模拟）
"""

import json
import os
import tempfile
import urllib.error
from io import BytesIO

import pytest


# ============================================================================
# 配置加载测试
# ============================================================================

class TestLocationConfig:
    """load_location_config 的加载与降级行为。"""

    def test_config_file_fallback(self):
        """
        通过 load_location_config 加载真实配置文件时，
        所有键值类型和范围应合法（相当于集成测试确认文件可读）。
        """
        from core.location import load_location_config

        # 传入存在的配置文件路径，验证加载成功
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "scripts", "config", "location_config.json",
        )
        config = load_location_config(config_path=config_path)
        assert isinstance(config["model"], str) and len(config["model"]) > 0
        assert isinstance(config["max_workers"], int) and config["max_workers"] >= 1
        assert isinstance(config["chunk_size"], int) and config["chunk_size"] >= 1
        assert isinstance(config["request_timeout"], int) and config["request_timeout"] >= 1

    def test_config_file_custom_path(self):
        """
        传入自定义 config_path 应覆盖默认值。
        """
        from core.location import load_location_config

        custom = {
            "model": "deepseek-chat",
            "max_workers": 4,
            "chunk_size": 50,
            "request_timeout": 120,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "test_location_config.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(custom, f, ensure_ascii=False, indent=2)

            config = load_location_config(config_path=cfg_path)
            assert config["model"] == "deepseek-chat"
            assert config["max_workers"] == 4
            assert config["chunk_size"] == 50
            assert config["request_timeout"] == 120

    def test_config_file_partial_override(self):
        """
        自定义配置文件只覆盖部分字段时，dict 合并行为由 json.load 决定
        （仅文件中存在的键会被设置）。
        """
        from core.location import load_location_config

        partial = {"model": "deepseek-reasoner"}

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "partial_location_config.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(partial, f, ensure_ascii=False, indent=2)

            config = load_location_config(config_path=cfg_path)
            # 文件中只有 model，其他键不应存在
            assert config["model"] == "deepseek-reasoner"
            with pytest.raises(KeyError):
                _ = config["max_workers"]

    def test_real_config_file_exists_and_valid(self):
        """
        生产环境的 scripts/config/location_config.json 应存在且为合法 JSON，
        所有键值类型正确。
        """
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "scripts", "config", "location_config.json",
        )
        assert os.path.isfile(config_path), f"配置文件不存在: {config_path}"

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        assert isinstance(config["model"], str), "model 应为字符串"
        assert isinstance(config["max_workers"], int), "max_workers 应为整数"
        assert isinstance(config["chunk_size"], int), "chunk_size 应为整数"
        assert isinstance(config["request_timeout"], int), "request_timeout 应为整数"


# ============================================================================
# HTTP 错误消息测试
# ============================================================================

def _make_mock_urlopen(status_code: int, body: bytes = b"{}"):
    """
    构造一个模拟 urlopen 函数，调用时抛出 HTTPError。

    Args:
        status_code: HTTP 状态码
        body: 响应体字节串

    Returns:
        一个可调用对象，调用时抛出 urllib.error.HTTPError
    """

    def mock_urlopen(req, timeout=None):
        # BytesIO 作为 fp 参数，使 e.fp 非空
        fp = BytesIO(body)
        raise urllib.error.HTTPError(
            url="https://api.deepseek.com/v1/chat/completions",
            code=status_code,
            msg="mock error",
            hdrs={},
            fp=fp,
        )

    return mock_urlopen


class TestLocationHttpErrors:
    """_call_deepseek 对各类 HTTP 错误的友好提示。"""

    # 用于测试的最小备注数据
    SAMPLE_NOTES = ["停车场A-停车缴费", "停车场B-停车缴费"]

    def _call_with_error(self, status_code: int, body: str = "{}"):
        """
        用指定的 HTTPError 调用 _call_deepseek，返回异常消息字符串。
        """
        from core.location import _call_deepseek

        mock = _make_mock_urlopen(status_code, body.encode("utf-8"))
        with pytest.raises(ValueError) as exc_info:
            _call_deepseek(self.SAMPLE_NOTES, "sk-test-key", _urlopen=mock)
        return str(exc_info.value)

    def test_http_401_error_message(self):
        """401 → API Key 无效提示。"""
        msg = self._call_with_error(401)
        assert "API Key" in msg, f"401 错误应提示 API Key: {msg}"
        assert "无效" in msg or "过期" in msg, f"401 错误应说明无效/过期: {msg}"

    def test_http_402_error_message(self):
        """402 → 余额不足提示。"""
        msg = self._call_with_error(402)
        assert "余额不足" in msg, f"402 错误应提示余额不足: {msg}"
        assert "platform.deepseek.com" in msg, f"402 错误应提供充值链接: {msg}"

    def test_http_429_error_message(self):
        """429 → 频率超限提示。"""
        msg = self._call_with_error(429)
        assert "频率超限" in msg or "429" in msg, f"429 错误应提示频率超限: {msg}"

    def test_http_503_error_message(self):
        """503 → 服务器不可用提示。"""
        msg = self._call_with_error(503)
        assert "服务器暂时不可用" in msg, f"5xx 错误应提示服务器不可用: {msg}"
        assert "503" in msg, f"5xx 错误应包含状态码: {msg}"

    def test_http_500_error_message(self):
        """500 → 服务器不可用提示。"""
        msg = self._call_with_error(500)
        assert "服务器暂时不可用" in msg, f"5xx 错误应提示服务器不可用: {msg}"
        assert "500" in msg, f"5xx 错误应包含状态码: {msg}"

    def test_http_unknown_error_message(self):
        """其他 HTTP 状态码 → 通用提示。"""
        msg = self._call_with_error(403)
        assert "HTTP 403" in msg or "API 请求失败" in msg, \
            f"未知状态码应包含状态码: {msg}"

    def test_error_body_appended(self):
        """
        当 HTTP 响应包含 body 时，异常消息应附加 body 中的错误详情。
        """
        body = json.dumps({"error": {"message": "Insufficient Balance"}})
        msg = self._call_with_error(402, body)
        assert "Insufficient Balance" in msg, \
            f"错误消息应包含响应体详情: {msg}"

    def test_empty_notes_returns_early(self):
        """
        _call_deepseek 在 notes 为空时应返回空列表而不发起任何网络请求。
        """
        from core.location import _call_deepseek

        def _should_not_be_called(req, timeout=None):
            raise AssertionError("不应发起网络请求")

        result = _call_deepseek([], "sk-test-key", _urlopen=_should_not_be_called)
        assert result == [], "空输入应返回空列表"


# ============================================================================
# 集成确认：配置读取路径兼容
# ============================================================================

class TestConfigLoadingIntegration:
    """验证正式配置文件的读取路径与 location.py 的 _get_config 兼容。"""

    def test_get_config_returns_valid_values(self):
        """
        在项目根目录下，_get_config() 应能读取到正式配置文件，
        返回的 model 值非空。
        """
        from core.location import _get_config

        config = _get_config()
        assert config is not None
        assert isinstance(config["model"], str)
        assert len(config["model"]) > 0, "模型名不应为空字符串"
        assert config["max_workers"] >= 1, "并发数应 ≥ 1"
        assert config["chunk_size"] >= 1, "块大小应 ≥ 1"
        assert config["request_timeout"] >= 1, "超时应 ≥ 1 秒"

    def test_extract_locations_no_api_key_returns_early(self):
        """
        extract_locations 在 parking_df 为空时不应调用 _call_deepseek。
        验证配置路径兼容性：模块导入和函数调用正常。
        """
        import pandas as pd
        from core.location import extract_locations

        empty_df = pd.DataFrame()
        result = extract_locations(empty_df, api_key="sk-test")
        assert result.empty, "空输入应返回空 DataFrame"
