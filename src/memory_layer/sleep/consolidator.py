"""Distill conversations into Atomic Facts during sleep cycle."""

from __future__ import annotations

import json
from uuid import UUID

import structlog

from memory_layer.graph.repository import GraphRepository
from memory_layer.llm.base import BaseLLMClient
from memory_layer.sleep.prompts import CONSOLIDATION_PROMPT

log = structlog.get_logger()


class Consolidator:
    """Consolidates ephemeral assertions into atomic facts."""

    def __init__(self, llm_client: BaseLLMClient, repository: GraphRepository) -> None:
        self._llm = llm_client
        self._repo = repository

    async def consolidate(self, user_id: UUID, batch_size: int = 50) -> int:
        """Consolidate unconsolidated assertions. Returns count of new atomic facts."""
        # Fetch unconsolidated FactualAssertion nodes
        nodes = await self._repo.get_nodes_by_label(user_id, "FactualAssertion", limit=batch_size)
        unconsolidated = [n for n in nodes if not n.get("consolidated")]

        if not unconsolidated:
            log.info("nothing_to_consolidate", user_id=str(user_id))
            return 0

        # Format assertions for LLM
        assertions_json = json.dumps([
            {"id": n["id"], "content": n.get("name", n.get("content", "")), "confidence": n.get("confidence", 1.0)}
            for n in unconsolidated
        ])

        prompt = CONSOLIDATION_PROMPT.format(assertions=assertions_json)
        result = await self._llm.complete_json(prompt)

        atomic_facts = result.get("atomic_facts", [])
        pruned_ids = result.get("pruned_ids", [])
        created_count = 0

        # Create new atomic fact nodes
        for fact in atomic_facts:
            new_node = await self._repo.create_node(user_id, "FactualAssertion", {
                "name": fact["content"],
                "content": fact["content"],
                "confidence": fact.get("confidence", 0.9),
                "consolidated": True,
                "atomic": True,
            })

            # Create SUPERSEDES edges from new fact to source nodes
            for source_id in fact.get("source_ids", []):
                try:
                    await self._repo.create_edge(
                        user_id, UUID(new_node["id"]), UUID(source_id), "SUPERSEDES",
                        {"confidence": 1.0, "source": "sleep_cycle"},
                    )
                except Exception:
                    pass  # Source node may have been pruned

            created_count += 1

        # Mark old assertions as consolidated
        for node in unconsolidated:
            await self._repo.update_node(user_id, UUID(node["id"]), {"consolidated": True})

        # Remove pruned ephemeral nodes
        for node_id in pruned_ids:
            try:
                await self._repo.delete_node(user_id, UUID(node_id))
            except Exception:
                pass

        log.info(
            "consolidation_complete",
            user_id=str(user_id),
            atomic_facts=created_count,
            pruned=len(pruned_ids),
            processed=len(unconsolidated),
        )
        return created_count
