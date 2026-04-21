"""Tests for application configuration."""

from __future__ import annotations

from memory_layer.config import Settings


class TestSettings:
    def test_defaults(self):
        s = Settings(fernet_keys=["test-key"])
        assert s.app_name == "memory-layer"
        assert s.app_env == "development"
        assert not s.is_production

    def test_production_detection(self):
        s = Settings(app_env="production", fernet_keys=["test"])
        assert s.is_production

    def test_fernet_keys_from_json_string(self):
        s = Settings(fernet_keys='["key1", "key2"]')
        assert s.fernet_keys == ["key1", "key2"]

    def test_fernet_keys_from_list(self):
        s = Settings(fernet_keys=["key1"])
        assert s.fernet_keys == ["key1"]
