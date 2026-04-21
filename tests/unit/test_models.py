"""Tests for Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from memory_layer.models.auth import RegisterRequest
from memory_layer.models.ingest import ContentType, IngestRequest
from memory_layer.models.keys import KeyCreateRequest, LLMProvider
from memory_layer.models.query import QueryRequest


class TestRegisterRequest:
    def test_valid(self):
        r = RegisterRequest(email="test@example.com", password="12345678", display_name="Test")
        assert r.email == "test@example.com"

    def test_short_password_fails(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="t@e.com", password="short", display_name="T")

    def test_invalid_email_fails(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", password="12345678", display_name="T")


class TestKeyCreateRequest:
    def test_valid(self):
        k = KeyCreateRequest(provider=LLMProvider.OPENAI, api_key="sk-12345")
        assert k.provider == LLMProvider.OPENAI

    def test_empty_key_fails(self):
        with pytest.raises(ValidationError):
            KeyCreateRequest(provider=LLMProvider.OPENAI, api_key="")


class TestIngestRequest:
    def test_valid(self):
        r = IngestRequest(content="Hello world")
        assert r.content_type == ContentType.TEXT

    def test_empty_content_fails(self):
        with pytest.raises(ValidationError):
            IngestRequest(content="")


class TestQueryRequest:
    def test_defaults(self):
        q = QueryRequest(query="What do I know?")
        assert q.max_hops == 3
        assert q.max_tokens == 4000

    def test_custom_values(self):
        q = QueryRequest(query="test", max_hops=5, max_tokens=8000)
        assert q.max_hops == 5
