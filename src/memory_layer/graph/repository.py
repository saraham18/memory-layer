"""High-level CRUD repository for the knowledge graph.

Every public method takes ``user_id`` as its first positional argument so
that **all** queries are automatically scoped to a single tenant.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from memory_layer.graph.driver import GraphDriver
from memory_layer.graph.queries import (
    COUNT_EDGES,
    COUNT_NODES_BY_LABEL,
    CREATE_EDGE,
    CREATE_NODE,
    DELETE_EDGE,
    DELETE_NODE,
    FULLTEXT_SEARCH,
    GET_EDGES,
    GET_NEIGHBORS,
    READ_NODE,
    UPDATE_NODE,
)
from memory_layer.graph.schemas import (
    FULLTEXT_INDEX_NAME,
    NodeLabel,
    RelationType,
)
from memory_layer.graph.transactions import execute_read, execute_write

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def _node_to_dict(record_value: Any) -> dict[str, Any]:
    """Convert a Neo4j node object to a plain dictionary."""
    node = record_value
    return dict(node.items())


class GraphRepository:
    """Tenant-scoped CRUD interface for the Neo4j knowledge graph."""

    def __init__(self, driver: GraphDriver) -> None:
        self._driver = driver

    @property
    def driver(self) -> GraphDriver:
        """Expose the underlying :class:`GraphDriver` for direct queries."""
        return self._driver

    # ------------------------------------------------------------------
    # Node CRUD
    # ------------------------------------------------------------------

    async def create_node(
        self,
        user_id: str,
        label: NodeLabel,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new node with the given label and properties.

        An ``id`` and ``created_at`` timestamp are generated automatically
        if not supplied in *properties*.
        """
        props = dict(properties or {})
        props.setdefault("id", str(uuid.uuid4()))
        props.setdefault("created_at", datetime.now(timezone.utc).isoformat())

        query = CREATE_NODE.format(label=label.value)
        params: dict[str, Any] = {
            "id": props.pop("id"),
            "user_id": user_id,
            "props": props,
        }

        records = await execute_write(self._driver, query, params)
        node_dict = _node_to_dict(records[0]["n"])
        log.info("node_created", user_id=user_id, label=label.value, node_id=node_dict["id"])
        return node_dict

    async def get_node(
        self,
        user_id: str,
        node_id: str,
    ) -> dict[str, Any] | None:
        """Return a single node by *node_id* scoped to *user_id*, or ``None``."""
        records = await execute_read(
            self._driver,
            READ_NODE,
            {"id": node_id, "user_id": user_id},
        )
        if not records:
            return None
        return _node_to_dict(records[0]["n"])

    async def update_node(
        self,
        user_id: str,
        node_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge *properties* into the node identified by *node_id*.

        Raises :class:`ValueError` if the node does not exist.
        """
        props = dict(properties)
        props["updated_at"] = datetime.now(timezone.utc).isoformat()

        records = await execute_write(
            self._driver,
            UPDATE_NODE,
            {"id": node_id, "user_id": user_id, "props": props},
        )
        if not records:
            raise ValueError(f"Node {node_id} not found for user {user_id}")
        node_dict = _node_to_dict(records[0]["n"])
        log.info("node_updated", user_id=user_id, node_id=node_id)
        return node_dict

    async def delete_node(
        self,
        user_id: str,
        node_id: str,
    ) -> bool:
        """Delete a node and all its relationships.  Returns ``True`` if deleted."""
        records = await execute_write(
            self._driver,
            DELETE_NODE,
            {"id": node_id, "user_id": user_id},
        )
        deleted: int = records[0]["deleted"] if records else 0
        if deleted:
            log.info("node_deleted", user_id=user_id, node_id=node_id)
        return deleted > 0

    # ------------------------------------------------------------------
    # Edge CRUD
    # ------------------------------------------------------------------

    async def create_edge(
        self,
        user_id: str,
        source_id: str,
        target_id: str,
        rel_type: RelationType,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a directed relationship from *source_id* to *target_id*."""
        props = dict(properties or {})
        props.setdefault("created_at", datetime.now(timezone.utc).isoformat())

        query = CREATE_EDGE.format(rel_type=rel_type.value)
        params: dict[str, Any] = {
            "source_id": source_id,
            "target_id": target_id,
            "user_id": user_id,
            "props": props,
        }

        records = await execute_write(self._driver, query, params)
        row = records[0]
        edge_dict: dict[str, Any] = {
            "rel_type": row["rel_type"],
            "source_id": row["source_id"],
            "target_id": row["target_id"],
            "properties": dict(row["props"]),
        }
        log.info(
            "edge_created",
            user_id=user_id,
            source_id=source_id,
            target_id=target_id,
            rel_type=rel_type.value,
        )
        return edge_dict

    async def get_edges(
        self,
        user_id: str,
        node_id: str,
    ) -> list[dict[str, Any]]:
        """Return all edges connected to *node_id* (both directions)."""
        records = await execute_read(
            self._driver,
            GET_EDGES,
            {"node_id": node_id, "user_id": user_id},
        )
        return [
            {
                "rel_type": r["rel_type"],
                "source_id": r["source_id"],
                "target_id": r["target_id"],
                "properties": dict(r["props"]),
            }
            for r in records
        ]

    async def delete_edge(
        self,
        user_id: str,
        source_id: str,
        target_id: str,
        rel_type: RelationType,
    ) -> bool:
        """Delete a specific directed relationship.  Returns ``True`` if deleted."""
        query = DELETE_EDGE.format(rel_type=rel_type.value)
        records = await execute_write(
            self._driver,
            query,
            {"source_id": source_id, "target_id": target_id, "user_id": user_id},
        )
        deleted: int = records[0]["deleted"] if records else 0
        if deleted:
            log.info(
                "edge_deleted",
                user_id=user_id,
                source_id=source_id,
                target_id=target_id,
                rel_type=rel_type.value,
            )
        return deleted > 0

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def fulltext_search(
        self,
        user_id: str,
        query: str,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Run a fulltext search scoped to *user_id*.

        Returns a list of dicts with ``node`` properties and ``score``.
        """
        records = await execute_read(
            self._driver,
            FULLTEXT_SEARCH,
            {
                "index_name": FULLTEXT_INDEX_NAME,
                "query": query,
                "user_id": user_id,
                "limit": limit,
            },
        )
        return [
            {**_node_to_dict(r["node"]), "score": r["score"]}
            for r in records
        ]

    # ------------------------------------------------------------------
    # Queries by label
    # ------------------------------------------------------------------

    async def get_nodes_by_label(
        self,
        user_id: str,
        label: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return all nodes of a given label for a user."""
        query = (
            f"MATCH (n:{label}) "
            "WHERE n.user_id = $user_id "
            "RETURN n "
            "ORDER BY n.created_at DESC "
            "SKIP $offset LIMIT $limit"
        )
        records = await execute_read(
            self._driver, query, {"user_id": user_id, "limit": limit, "offset": offset}
        )
        return [_node_to_dict(r["n"]) for r in records]

    async def export_graph(
        self,
        user_id: str,
    ) -> dict[str, Any]:
        """Export all nodes and edges for a user."""
        node_query = "MATCH (n) WHERE n.user_id = $user_id RETURN n"
        edge_query = (
            "MATCH (a)-[r]-(b) "
            "WHERE a.user_id = $user_id AND b.user_id = $user_id "
            "RETURN DISTINCT a.id AS source_id, b.id AS target_id, "
            "       type(r) AS relationship, properties(r) AS props"
        )
        node_records = await execute_read(self._driver, node_query, {"user_id": user_id})
        edge_records = await execute_read(self._driver, edge_query, {"user_id": user_id})

        nodes = [_node_to_dict(r["n"]) for r in node_records]
        edges = [
            {
                "source_id": r["source_id"],
                "target_id": r["target_id"],
                "relationship": r["relationship"],
                **dict(r["props"]),
            }
            for r in edge_records
        ]
        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def get_stats(
        self,
        user_id: str,
    ) -> dict[str, Any]:
        """Return aggregate counts for the given user's sub-graph."""
        stats: dict[str, Any] = {"user_id": user_id, "nodes": {}, "edges": 0}

        for label in NodeLabel:
            query = COUNT_NODES_BY_LABEL.format(label=label.value)
            records = await execute_read(
                self._driver, query, {"user_id": user_id}
            )
            stats["nodes"][label.value] = records[0]["count"] if records else 0

        edge_records = await execute_read(
            self._driver, COUNT_EDGES, {"user_id": user_id}
        )
        stats["edges"] = edge_records[0]["count"] if edge_records else 0

        return stats

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    async def get_neighbors(
        self,
        user_id: str,
        node_id: str,
        max_hops: int = 2,
        rel_types: list[RelationType] | None = None,
    ) -> list[dict[str, Any]]:
        """BFS traversal returning distinct neighbours up to *max_hops* away.

        Optionally filter by *rel_types*.  Results include the neighbour
        node properties and the connecting relationship metadata.
        """
        if rel_types:
            rel_filter = ":" + "|".join(rt.value for rt in rel_types)
        else:
            rel_filter = ""

        query = GET_NEIGHBORS.format(rel_filter=rel_filter, max_hops=max_hops)
        records = await execute_read(
            self._driver,
            query,
            {"node_id": node_id, "user_id": user_id},
        )
        return [
            {
                **_node_to_dict(r["neighbor"]),
                "rel_type": r["rel_type"],
                "source_id": r["source_id"],
                "target_id": r["target_id"],
            }
            for r in records
        ]
