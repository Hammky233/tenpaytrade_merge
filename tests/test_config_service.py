"""
测试 scripts/service/config_service.py 配置读写服务。

关键隔离策略：
  每个测试用例通过 monkeypatch.setattr 将 get_user_config_dir() 重定向到 tmp_path，
  确保 save_*_config() 不会写入真实 scripts/config/ 目录。

验证点：
  - 保存 -> 读取闭环
  - 缺失必填字段返回错误信息
  - 磁盘文件写入在 tmp_path 内
  - 读取始终返回 dict（从用户配置或内置默认）
"""

import os
import pytest

# 测试用有效停车配置
_VALID_PARKING_CONFIG = {
    "备注2关键词": ["停车缴费", "停车费", "停车"],
    "排除关键词": [],
    "对手侧账户名称关键词": ["停车"],
    "车牌省份简称": ["京", "沪", "粤"],
}

# 测试用有效时段配置
_VALID_TIME_PERIOD_CONFIG = {
    "时段": [
        {"name": "凌晨", "start": "00:00", "end": "06:00"},
        {"name": "早上", "start": "06:00", "end": "12:00"},
    ],
}


def _mock_user_config_dir(tmp_path, monkeypatch):
    """将 get_user_config_dir 重定向到 tmp_path，不写入真实配置目录。"""
    monkeypatch.setattr("utils.paths.get_user_config_dir", lambda: str(tmp_path))


# ============================================================================
# 停车缴费配置
# ============================================================================


class TestParkingConfig:
    """停车缴费配置读写测试（全隔离）。"""

    def test_save_and_read_back(self, tmp_path, monkeypatch):
        """写入有效配置后，get 能读取同一份配置。"""
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import save_parking_config, get_parking_config

        result = save_parking_config(_VALID_PARKING_CONFIG)
        assert result == "ok"

        # 验证文件落在 tmp_path 而非真实配置目录
        saved_path = os.path.join(str(tmp_path), "parking_config.json")
        assert os.path.isfile(saved_path), f"配置文件应在 tmp_path 内: {saved_path}"

        # 验证读取回的数据是 dict
        loaded = get_parking_config()
        assert isinstance(loaded, dict)
        assert "备注2关键词" in loaded

    def test_save_then_override(self, tmp_path, monkeypatch):
        """覆盖写入已存在的配置。"""
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import save_parking_config

        config_a = dict(_VALID_PARKING_CONFIG, 车牌省份简称=["京"])
        assert save_parking_config(config_a) == "ok"

        config_b = dict(_VALID_PARKING_CONFIG, 车牌省份简称=["粤", "沪"])
        assert save_parking_config(config_b) == "ok"

        import json
        with open(os.path.join(str(tmp_path), "parking_config.json"), "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["车牌省份简称"] == ["粤", "沪"]

    def test_missing_field_returns_error(self, tmp_path, monkeypatch):
        """缺少必填字段时返回错误信息，不写文件。"""
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import save_parking_config

        result = save_parking_config({"备注2关键词": ["停车"]})
        assert result.startswith("缺少必填字段")
        # 断言未写入文件
        assert not os.path.isfile(os.path.join(str(tmp_path), "parking_config.json"))

    def test_get_returns_dict_without_save(self, tmp_path, monkeypatch):
        """未保存过配置时，get 返回内置默认配置（dict）。"""
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import get_parking_config

        config = get_parking_config()
        assert isinstance(config, dict)
        # 内置默认应包含这些字段
        for field in ("备注2关键词", "排除关键词", "对手侧账户名称关键词", "车牌省份简称"):
            assert field in config, f"内置默认配置应包含 {field}"

    def test_get_returns_dict_on_error(self, tmp_path, monkeypatch):
        """出现异常时返回 {"error": ...}。"""
        # 让 load_parking_config 抛异常
        def _broken_load(*args, **kwargs):
            raise RuntimeError("模拟错误")

        _mock_user_config_dir(tmp_path, monkeypatch)
        monkeypatch.setattr("core.parking.load_parking_config", _broken_load)
        from service.config_service import get_parking_config

        result = get_parking_config()
        assert isinstance(result, dict)
        assert "error" in result


# ============================================================================
# 时段分类配置
# ============================================================================


class TestTimePeriodConfig:
    """时段分类配置读写测试（全隔离）。"""

    def test_save_and_read_back(self, tmp_path, monkeypatch):
        """写入有效配置后，get 能读取同一份配置。"""
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import save_time_period_config, get_time_period_config

        result = save_time_period_config(_VALID_TIME_PERIOD_CONFIG)
        assert result == "ok"

        saved_path = os.path.join(str(tmp_path), "time_period_config.json")
        assert os.path.isfile(saved_path)

        loaded = get_time_period_config()
        assert isinstance(loaded, dict)
        assert "时段" in loaded

    def test_missing_periods_field_returns_error(self, tmp_path, monkeypatch):
        """缺少"时段"字段时返回错误。"""
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import save_time_period_config

        result = save_time_period_config({"时段": "not_a_list"})
        assert result == "缺少必填字段: 时段"
        assert not os.path.isfile(os.path.join(str(tmp_path), "time_period_config.json"))

    def test_invalid_period_entry_returns_error(self, tmp_path, monkeypatch):
        """时段条目缺少 name/start/end 时返回错误。"""
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import save_time_period_config

        result = save_time_period_config({"时段": [{"name": "凌晨"}]})
        assert result == "每个时段必须包含 name, start, end"
        assert not os.path.isfile(os.path.join(str(tmp_path), "time_period_config.json"))

    def test_get_returns_dict_without_save(self, tmp_path, monkeypatch):
        """未保存过配置时，返回内置默认配置。"""
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import get_time_period_config

        config = get_time_period_config()
        assert isinstance(config, dict)
        assert "时段" in config
        assert len(config["时段"]) > 0

    def test_monkeypatch_redirects_to_tmp_path(self, tmp_path, monkeypatch):
        """验证 monkeypatch 将文件写入重定向到 tmp_path。"""
        _mock_user_config_dir(tmp_path, monkeypatch)
        from service.config_service import save_parking_config

        save_parking_config(_VALID_PARKING_CONFIG)

        # 验证文件写入 tmp_path
        saved_path = os.path.join(str(tmp_path), "parking_config.json")
        assert os.path.isfile(saved_path), (
            f"文件应写入 tmp_path: {saved_path}"
        )
