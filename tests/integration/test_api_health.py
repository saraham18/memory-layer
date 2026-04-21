"""Integration tests for health endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with mocked Neo4j driver."""
    with patch("memory_layer.main.GraphDriver") as mock_driver_cls, \
         patch("memory_layer.main.ensure_indexes"):
        mock_driver = MagicMock()
        mock_driver.close = AsyncMock()
        mock_driver_cls.return_value = mock_driver

        from memory_layer.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


class TestHealthEndpoints:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
