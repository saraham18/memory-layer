"""Conflict resolver — uses the LLM to resolve contradictions in the graph."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from memory_layer.graph.repository import GraphRepository
from memory_layer.graph.schemas import NodeLabel, RelationType
from memory_layer.integrity.prompts import RESOLUTION_PROMPT, RESOLUTION_SYSTEM
from memory_layer.llm.base import BaseLLMClient

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_VALID_STRATEGIES = frozenset({"keep_a", "keep_b", "merge", "flag"})


class ConflictResolver:
    """Resolve contradiction edges in the knowledge graph.

    Parameters
    ----------
    llm_client:
        An LLM client used for resolution reasoning.
    repository:
        The tenant-scoped graph repository.
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        repository: GraphRepository,
    ) -> None:
        self._llm = llm_client
        self._repo = repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def resolve(
        self,
        user_id: UUID,
        node_id_a: UUID,
        node_id_b: UUID,
    ) -> dict[str, Any]:
        """Use the LLM to resolve a contradiction between two nodes.

        Returns a dict describing the resolution:
        ``{"strategy": ..., "merged_content": ..., "reasoning": ..., "resolved": bool}``
        """
        uid = str(user_id)
        nid_a = str(node_id_a)
        nid_b = str(node_id_b)

        node_a = await self._repo.get_node(uid, nid_a)
        node_b = await self._repo.get_node(uid, nid_b)

        if node_a is None or node_b is None:
            missing = nid_a if node_a is None else nid_b
            log.warning("resolve_node_not_found", user_id=uid, missing_node_id=missing)
            return {
                "strategy": "flag",
                "merged_content": None,
                "reasoning": f"Node {missing} not found.",
                "resolved": False,
            }

        assertion_a = node_a.get("content") or node_a.get("name", "")
        assertion_b = node_b.get("content") or node_b.get("name", "")

        resolution = await self._ask_llm(assertion_a, assertion_b)
        strategy = resolution.get("strategy", "flag")

        if strategy not in _VALID_STRATEGIES:
            log.warning("unexpected_strategy", strategy=strategy, fallback="flag")
            strategy = "flag"

        resolved = False

        if strategy == "keep_a":
            resolved = await self._apply_keep(uid, winner_id=nid_a, loser_id=nid_b)

        elif strategy == "keep_b":
            resolved = await self._apply_keep(uid, winner_id=nid_b, loser_id=nid_a)

        elif strategy == "merge":
            merged_content = resolution.get("merged_content")
            if merged_content:
                resolved = await self._apply_merge(
                    uid, nid_a, nid_b, merged_content,
                )
            else:
                log.warning("merge_missing_content", user_id=uid)

        # "flag" — nothing to do automatically.

        log.info(
            "conflict_resolved",
            user_id=uid,
            node_a=nid_a,
            node_b=nid_b,
            strategy=strategy,
            resolved=resolved,
        )

        return {
            "strategy": strategy,
            "merged_content": resolution.get("merged_content"),
            "reasoning": resolution.get("reasoning", ""),
            "resolved": resolved,
        }

    async def auto_resolve(self, user_id: UUID) -> int:
        """Find all ``CONTRADICTS`` edges for *user_id* and attempt resolution.

        Returns the number of contradictions successfully resolved.
        """
        uid = str(user_id)
        stats = await self._repo.get_stats(uid)

        # We need to find CONTRADICTS edges.  Walk all FactualAssertion nodes
        # and inspect their edges.
        resolved_count = 0
        seen_pairs: set[tuple[str, str]] = set()

        # Search for factual assertion nodes to find contradiction edges.
        fa_nodes = await self._repo.fulltext_search(uid, "*", limit=500)

        for node in fa_nodes:
            node_id = node.get("id", "")
            if not node_id:
                continue

            edges = await self._repo.get_edges(uid, node_id)
            for edge in edges:
                if edge.get("rel_type") != RelationType.CONTRADICTS:
                    continue

                source_id = edge["source_id"]
                target_id = edge["target_id"]
                pair = tuple(sorted((source_id, target_id)))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                result = await self.resolve(
                    user_id,
                    UUID(source_id),
                    UUID(target_id),
                )
                if result.get("resolved"):
                    resolved_count += 1

        log.info(
            "auto_resolve_completed",
            user_id=uid,
            total_contradictions=len(seen_pairs),
            resolved=resolved_count,
        )
        return resolved_count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ask_llm(
        self,
        assertion_a: str,
        assertion_b: str,
    ) -> dict[str, Any]:
        """Query the LLM for a resolution strategy."""
        prompt = RESOLUTION_PROMPT.format(
            assertion_a=assertion_a,
            assertion_b=assertion_b,
        )
        try:
            return await self._llm.complete_json(
                prompt,
                system=RESOLUTION_SYSTEM,
                temperature=0.0,
                max_tokens=512,
            )
        except Exception:
            log.exception("resolution_llm_failed")
            return {"strategy": "flag", "merged_content": None, "reasoning": "LLM call failed."}

    async def _apply_keep(
        self,
        user_id: str,
        winner_id: str,
        loser_id: str,
    ) -> bool:
        """Keep the winner, mark loser as superseded."""
        try:
            # Remove the CONTRADICTS edge by creating a SUPERSEDES edge instead.
            await self._repo.create_edge(
                user_id,
                source_id=winner_id,
                target_id=loser_id,
                rel_type=RelationType.SUPERSEDES,
                properties={"source": "conflict_resolver"},
            )
            # Lower the confidence of the losing node.
            await self._repo.update_node(user_id, loser_id, {"confidence": 0.1})
            return True
        except Exception:
            log.exception("apply_keep_failed", user_id=user_id, winner_id=winner_id)
            return False

    async def _apply_merge(
        self,
        user_id: str,
        node_id_a: str,
        node_id_b: str,
        merged_content: str,
    ) -> bool:
        """Create a merged node and supersede both originals."""
        try:
            merged_node = await self._repo.create_node(
                user_id,
                NodeLabel.FACTUAL_ASSERTION,
                {
                    "content": merged_content,
                    "confidence": 0.9,
                    "source": "conflict_resolver_merge",
                },
            )
            # The merged node supersedes both originals.
            for old_id in (node_id_a, node_id_b):
                await self._repo.create_edge(
                    user_id,
                    source_id=merged_node["id"],
                    target_id=old_id,
                    rel_type=RelationType.SUPERSEDES,
                    properties={"source": "conflict_resolver"},
                )
                await self._repo.update_node(user_id, old_id, {"confidence": 0.1})
            return True
        except Exception:
            log.exception(
                "apply_merge_failed",
                user_id=user_id,
                node_a=node_id_a,
                node_b=node_id_b,
            )
            return False
