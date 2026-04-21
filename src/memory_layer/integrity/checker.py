"""Integrity checker — validates new extractions against the existing graph.

Before committing newly extracted nodes and edges the checker searches for
similar existing nodes.  For ``FactualAssertion`` nodes it uses the LLM to
classify the relationship (compatible / update / contradiction) and takes the
appropriate action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import structlog

from memory_layer.graph.repository import GraphRepository
from memory_layer.graph.schemas import NodeLabel, RelationType
from memory_layer.integrity.prompts import (
    CONTRADICTION_CHECK_PROMPT,
    CONTRADICTION_CHECK_SYSTEM,
)
from memory_layer.llm.base import BaseLLMClient

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@dataclass
class _ExtractionResult:
    """Lightweight view of an extraction result accepted by the checker.

    The caller may pass any object that exposes ``ingest_id``, ``nodes`` and
    ``edges`` attributes — or a plain dict with the same keys.  This helper
    normalises access.
    """

    ingest_id: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


def _as_extraction(extraction_result: Any) -> _ExtractionResult:
    """Coerce an extraction result into a normalised dataclass."""
    if isinstance(extraction_result, dict):
        return _ExtractionResult(
            ingest_id=str(extraction_result["ingest_id"]),
            nodes=list(extraction_result["nodes"]),
            edges=list(extraction_result["edges"]),
        )
    return _ExtractionResult(
        ingest_id=str(extraction_result.ingest_id),
        nodes=list(extraction_result.nodes),
        edges=list(extraction_result.edges),
    )


@dataclass
class CommitSummary:
    """Counters returned by :meth:`IntegrityChecker.check_and_commit`."""

    committed: int = 0
    contradictions: int = 0
    merged: int = 0
    # Maps original temporary node id -> committed graph node id
    id_map: dict[str, str] = field(default_factory=dict)


class IntegrityChecker:
    """Check new extraction results for conflicts before committing to the graph.

    Parameters
    ----------
    llm_client:
        An LLM client used for contradiction classification.
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

    async def check_and_commit(
        self,
        user_id: UUID,
        extraction_result: Any,
    ) -> dict[str, Any]:
        """Validate *extraction_result* and commit accepted nodes/edges.

        Workflow
        -------
        1. For each new node, search the graph for similar existing nodes.
        2. For ``FactualAssertion`` nodes, use the LLM to classify the
           relationship with each similar existing node.
        3. *compatible* — auto-merge (boost existing node confidence).
        4. *contradiction* — flag by creating a ``CONTRADICTS`` edge.
        5. *update* — commit the new node and create a ``SUPERSEDES`` edge.
        6. Commit all remaining new nodes and edges.
        7. Return a summary dict.
        """
        uid = str(user_id)
        er = _as_extraction(extraction_result)
        summary = CommitSummary()

        log.info(
            "integrity_check_started",
            user_id=uid,
            ingest_id=er.ingest_id,
            new_nodes=len(er.nodes),
            new_edges=len(er.edges),
        )

        # Track which new-node indices have been fully handled (merged / contradicted).
        handled_indices: set[int] = set()

        # --- Phase 1: compare each new node against existing graph --------
        for idx, new_node in enumerate(er.nodes):
            label = new_node.get("label", "")
            search_text = self._search_text_for(new_node)
            if not search_text:
                continue

            existing_matches = await self._repo.fulltext_search(
                uid, search_text, limit=5,
            )
            if not existing_matches:
                continue

            is_factual = label == NodeLabel.FACTUAL_ASSERTION

            for existing in existing_matches:
                if not is_factual:
                    # Non-factual nodes: simple duplicate-merge heuristic.
                    if self._names_match(new_node, existing):
                        await self._merge_into_existing(uid, new_node, existing)
                        summary.merged += 1
                        summary.id_map[new_node.get("id", "")] = existing["id"]
                        handled_indices.add(idx)
                        break
                    continue

                # Factual assertion — ask the LLM.
                classification = await self._classify(
                    existing_assertion=existing.get("content", ""),
                    new_assertion=new_node.get("content", ""),
                )

                if classification == "compatible":
                    await self._merge_into_existing(uid, new_node, existing)
                    summary.merged += 1
                    summary.id_map[new_node.get("id", "")] = existing["id"]
                    handled_indices.add(idx)
                    break

                if classification == "contradiction":
                    # Commit the new node so we can link to it.
                    committed = await self._commit_node(uid, new_node)
                    summary.id_map[new_node.get("id", "")] = committed["id"]
                    await self._repo.create_edge(
                        uid,
                        source_id=committed["id"],
                        target_id=existing["id"],
                        rel_type=RelationType.CONTRADICTS,
                        properties={"source": "integrity_checker"},
                    )
                    summary.contradictions += 1
                    summary.committed += 1
                    handled_indices.add(idx)
                    break

                if classification == "update":
                    committed = await self._commit_node(uid, new_node)
                    summary.id_map[new_node.get("id", "")] = committed["id"]
                    await self._repo.create_edge(
                        uid,
                        source_id=committed["id"],
                        target_id=existing["id"],
                        rel_type=RelationType.SUPERSEDES,
                        properties={"source": "integrity_checker"},
                    )
                    summary.committed += 1
                    handled_indices.add(idx)
                    break

        # --- Phase 2: commit remaining new nodes --------------------------
        for idx, new_node in enumerate(er.nodes):
            if idx in handled_indices:
                continue
            committed = await self._commit_node(uid, new_node)
            summary.id_map[new_node.get("id", "")] = committed["id"]
            summary.committed += 1

        # --- Phase 3: commit edges (remapping ids) ------------------------
        for edge in er.edges:
            source_id = summary.id_map.get(edge.get("source_id", ""), edge.get("source_id", ""))
            target_id = summary.id_map.get(edge.get("target_id", ""), edge.get("target_id", ""))
            rel_type_raw = edge.get("rel_type") or edge.get("relationship", "RELATED_TO")
            try:
                rel_type = RelationType(rel_type_raw)
            except ValueError:
                rel_type = RelationType.RELATED_TO

            props = {
                k: v for k, v in edge.items()
                if k not in {"source_id", "target_id", "rel_type", "relationship"}
                and isinstance(v, (str, int, float, bool))
            }
            await self._repo.create_edge(uid, source_id, target_id, rel_type, props)

        log.info(
            "integrity_check_completed",
            user_id=uid,
            ingest_id=er.ingest_id,
            committed=summary.committed,
            contradictions=summary.contradictions,
            merged=summary.merged,
        )

        return {
            "committed": summary.committed,
            "contradictions": summary.contradictions,
            "merged": summary.merged,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _search_text_for(node: dict[str, Any]) -> str:
        """Return the best text to use for fulltext search against the graph."""
        return (
            node.get("content")
            or node.get("name")
            or node.get("description")
            or ""
        )

    @staticmethod
    def _names_match(new_node: dict[str, Any], existing: dict[str, Any]) -> bool:
        """Quick heuristic: check whether two nodes refer to the same entity."""
        new_name = (new_node.get("name") or "").strip().lower()
        existing_name = (existing.get("name") or "").strip().lower()
        return bool(new_name and new_name == existing_name)

    async def _classify(
        self,
        existing_assertion: str,
        new_assertion: str,
    ) -> str:
        """Use the LLM to classify the relationship between two assertions.

        Returns one of ``"contradiction"``, ``"update"``, or ``"compatible"``.
        """
        prompt = CONTRADICTION_CHECK_PROMPT.format(
            existing_assertion=existing_assertion,
            new_assertion=new_assertion,
        )
        try:
            result = await self._llm.complete_json(
                prompt,
                system=CONTRADICTION_CHECK_SYSTEM,
                temperature=0.0,
                max_tokens=256,
            )
            classification = result.get("classification", "compatible")
            if classification not in {"contradiction", "update", "compatible"}:
                log.warning(
                    "unexpected_classification",
                    classification=classification,
                    fallback="compatible",
                )
                return "compatible"
            return classification
        except Exception:
            log.exception("classification_failed")
            return "compatible"

    async def _merge_into_existing(
        self,
        user_id: str,
        new_node: dict[str, Any],
        existing: dict[str, Any],
    ) -> None:
        """Boost the confidence of an existing node after a compatible match."""
        current_confidence = float(existing.get("confidence", 0.5))
        new_confidence = float(new_node.get("confidence", 0.5))
        # Weighted average biased toward the higher value.
        merged_confidence = min(1.0, (current_confidence + new_confidence) / 2 + 0.05)
        await self._repo.update_node(
            user_id,
            existing["id"],
            {"confidence": merged_confidence},
        )
        log.debug(
            "node_merged",
            user_id=user_id,
            existing_id=existing["id"],
            merged_confidence=merged_confidence,
        )

    async def _commit_node(
        self,
        user_id: str,
        node: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist a single new node to the graph."""
        label_raw = node.get("label", NodeLabel.ENTITY)
        try:
            label = NodeLabel(label_raw)
        except ValueError:
            label = NodeLabel.ENTITY

        props = {
            k: v for k, v in node.items()
            if k not in {"label"}
            and isinstance(v, (str, int, float, bool))
        }
        return await self._repo.create_node(user_id, label, props)
