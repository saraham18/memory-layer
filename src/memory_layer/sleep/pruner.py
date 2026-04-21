"""Ephemeral node removal during sleep cycle."""

from __future__ import annotations

from uuid import UUID

import structlog

from memory_layer.graph.repository import GraphRepository

log = structlog.get_logger()


class Pruner:
    """Removes orphaned and low-confidence ephemeral nodes."""

    def __init__(self, repository: GraphRepository) -> None:
        self._repo = repository

    async def prune(self, user_id: UUID, min_confidence: float = 0.2) -> int:
        """Remove orphaned and very low-confidence nodes. Returns count pruned."""
        pruned = 0

        # Get all user nodes with low confidence
        stats = await self._repo.get_stats(user_id)
        for label in ["FactualAssertion", "Entity", "Concept"]:
            nodes = await self._repo.get_nodes_by_label(user_id, label, limit=1000)
            for node in nodes:
                confidence = node.get("confidence", 1.0)
                if confidence < min_confidence:
                    await self._repo.delete_node(user_id, UUID(node["id"]))
                    pruned += 1
                    continue

                # Check for orphaned nodes (no edges)
                edges = await self._repo.get_edges(user_id, UUID(node["id"]))
                if not edges and node.get("consolidated"):
                    await self._repo.delete_node(user_id, UUID(node["id"]))
                    pruned += 1

        log.info("prune_complete", user_id=str(user_id), pruned=pruned)
        return pruned
