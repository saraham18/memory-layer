"""End-to-end pipeline test (requires running Neo4j and LLM keys)."""

from __future__ import annotations

import os

import pytest

# Skip all e2e tests if no Neo4j connection configured
pytestmark = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="NEO4J_URI not set — skip e2e tests",
)


class TestFullPipeline:
    """Full integration test: register -> store key -> ingest -> query."""

    @pytest.fixture
    def api_url(self):
        return os.getenv("API_URL", "http://localhost:8000")

    async def test_register_ingest_query(self, api_url):
        """This test requires a running server + Neo4j + valid LLM key."""
        import httpx

        async with httpx.AsyncClient(base_url=api_url) as client:
            # Register
            resp = await client.post("/api/v1/auth/register", json={
                "email": "e2e-test@example.com",
                "password": "test-password-123",
                "display_name": "E2E Test",
            })
            if resp.status_code == 409:
                pass  # Already registered
            else:
                assert resp.status_code == 201

            # Login
            resp = await client.post("/api/v1/auth/token", json={
                "email": "e2e-test@example.com",
                "password": "test-password-123",
            })
            assert resp.status_code == 200
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Health
            resp = await client.get("/health")
            assert resp.status_code == 200

            # Store API key (if configured)
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                resp = await client.post("/api/v1/keys", json={
                    "provider": "openai",
                    "api_key": api_key,
                    "label": "e2e-test",
                }, headers=headers)
                assert resp.status_code in (201, 409)

                # Ingest
                resp = await client.post("/api/v1/ingest", json={
                    "content": "The capital of France is Paris. Paris is known for the Eiffel Tower.",
                    "content_type": "text",
                }, headers=headers)
                assert resp.status_code == 202

                # Query
                resp = await client.post("/api/v1/query", json={
                    "query": "What do I know about France?",
                }, headers=headers)
                assert resp.status_code == 200
                assert "master_context" in resp.json()
