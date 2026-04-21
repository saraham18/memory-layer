"""Shared test fixtures."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from memory_layer.config import Settings
from memory_layer.core.security import KeyEncryptor
from memory_layer.llm.base import BaseLLMClient, LLMResponse


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_name="test",
        app_env="test",
        debug=True,
        secret_key="test-secret-key-at-least-32-chars-long",
        jwt_secret_key="test-jwt-secret-key-at-least-32-chars",
        jwt_algorithm="HS256",
        jwt_expiry_hours=1,
        fernet_keys=[KeyEncryptor.generate_key()],
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="test",
        neo4j_database="neo4j",
    )


@pytest.fixture
def encryptor(settings: Settings) -> KeyEncryptor:
    return KeyEncryptor(settings.fernet_keys)


@pytest.fixture
def user_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_repository() -> MagicMock:
    """Mock GraphRepository for unit tests."""
    repo = MagicMock()
    repo.create_node = AsyncMock(return_value={
        "id": str(uuid4()),
        "label": "Entity",
        "name": "test",
        "properties": {},
        "confidence": 1.0,
        "created_at": "2024-01-01T00:00:00Z",
    })
    repo.get_node = AsyncMock(return_value=None)
    repo.update_node = AsyncMock(return_value=None)
    repo.delete_node = AsyncMock(return_value=True)
    repo.create_edge = AsyncMock(return_value={
        "source_id": str(uuid4()),
        "target_id": str(uuid4()),
        "relationship": "RELATED_TO",
        "confidence": 1.0,
        "created_at": "2024-01-01T00:00:00Z",
        "source": "test",
    })
    repo.get_edges = AsyncMock(return_value=[])
    repo.delete_edge = AsyncMock(return_value=True)
    repo.fulltext_search = AsyncMock(return_value=[])
    repo.get_stats = AsyncMock(return_value={
        "total_nodes": 0,
        "total_edges": 0,
        "node_counts": {},
        "edge_counts": {},
    })
    repo.get_nodes_by_label = AsyncMock(return_value=[])
    repo.get_neighbors = AsyncMock(return_value=[])
    repo.export_graph = AsyncMock(return_value={"nodes": [], "edges": []})

    # Mock driver for user_manager direct session access
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.run = AsyncMock(return_value=MagicMock(single=MagicMock(return_value=None)))
    repo.driver = MagicMock()
    repo.driver.session = MagicMock(return_value=mock_session)

    return repo


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock LLM client for unit tests."""
    client = MagicMock(spec=BaseLLMClient)
    client.complete = AsyncMock(return_value=LLMResponse(
        content="test response",
        model="test-model",
        usage={"prompt_tokens": 10, "completion_tokens": 20},
    ))
    client.complete_json = AsyncMock(return_value={"result": "test"})
    client.provider = "openai"
    return client
