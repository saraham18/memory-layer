"""FastMCP server mounted on FastAPI at /mcp."""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP

from memory_layer.api.dependencies import get_graph_driver
from memory_layer.config import get_settings
from memory_layer.core.key_manager import KeyManager
from memory_layer.core.security import KeyEncryptor
from memory_layer.graph.repository import GraphRepository
from memory_layer.mcp.auth import validate_mcp_token
from memory_layer.mcp.tools import memory_ingest, memory_query, memory_status
from memory_layer.models.mcp import MCPIngestInput, MCPQueryInput

log = structlog.get_logger()


def create_mcp_app() -> FastMCP:
    """Create the MCP server with memory tools."""
    mcp = FastMCP("Memory Layer")

    def _get_deps(token: str):
        user_id = validate_mcp_token(token)
        driver = get_graph_driver()
        repo = GraphRepository(driver)
        settings = get_settings()
        encryptor = KeyEncryptor(settings.fernet_keys)
        key_mgr = KeyManager(repo, encryptor)
        return user_id, repo, key_mgr

    @mcp.tool()
    async def ingest(content: str, token: str, content_type: str = "text", metadata: dict | None = None) -> str:
        """Ingest content into your persistent knowledge graph. Extracts entities, goals, assertions, and relationships."""
        try:
            user_id, repo, key_mgr = _get_deps(token)
            input_data = MCPIngestInput(content=content, content_type=content_type, metadata=metadata)
            result = await memory_ingest(user_id, input_data, repo, key_mgr)
            if "error" in result:
                return f"Error: {result['error']}"
            return f"Ingested successfully. Nodes created: {result['nodes_created']}, Contradictions: {result['contradictions']}"
        except Exception as e:
            log.error("mcp_ingest_error", error=str(e))
            return f"Error: {e}"

    @mcp.tool()
    async def query(query_text: str, token: str, max_hops: int = 3, max_tokens: int = 4000) -> str:
        """Query your knowledge graph. Returns relevant context from your stored memories."""
        try:
            user_id, repo, key_mgr = _get_deps(token)
            input_data = MCPQueryInput(query=query_text, max_hops=max_hops, max_tokens=max_tokens)
            result = await memory_query(user_id, input_data, repo, key_mgr)
            if "error" in result:
                return f"Error: {result['error']}"
            return result["master_context"]
        except Exception as e:
            log.error("mcp_query_error", error=str(e))
            return f"Error: {e}"

    @mcp.tool()
    async def status(token: str) -> str:
        """Check the status of your knowledge graph — node/edge counts and connectivity."""
        try:
            user_id, repo, _ = _get_deps(token)
            result = await memory_status(user_id, repo)
            return f"Connected: {result['connected']}, Nodes: {result['graph_nodes']}, Edges: {result['graph_edges']}"
        except Exception as e:
            log.error("mcp_status_error", error=str(e))
            return f"Error: {e}"

    return mcp
