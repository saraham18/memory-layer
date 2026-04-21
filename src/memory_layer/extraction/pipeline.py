"""Main extraction pipeline orchestrator."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from memory_layer.extraction.edge_extractor import EdgeExtractor
from memory_layer.extraction.node_extractor import NodeExtractor
from memory_layer.extraction.spacy_config import chunk_text
from memory_layer.extraction.validators import (
    deduplicate_nodes,
    normalize_name,
    validate_relationships,
)
from memory_layer.graph.repository import GraphRepository
from memory_layer.graph.schemas import NodeLabel, RelationType
from memory_layer.llm.base import BaseLLMClient
from memory_layer.models.ingest import ContentType

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Mapping from extraction label strings to graph NodeLabel enum members.
_LABEL_MAP: dict[str, NodeLabel] = {
    "Entity": NodeLabel.ENTITY,
    "UserGoal": NodeLabel.USER_GOAL,
    "FactualAssertion": NodeLabel.FACTUAL_ASSERTION,
    "Concept": NodeLabel.CONCEPT,
}


@dataclass
class ExtractionResult:
    """Outcome of a full extraction pipeline run."""

    ingest_id: UUID
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class ExtractionPipeline:
    """Orchestrates chunking, extraction, deduplication, and graph commit."""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        repository: GraphRepository,
    ) -> None:
        self._llm = llm_client
        self._repository = repository
        self._node_extractor = NodeExtractor(llm_client)
        self._edge_extractor = EdgeExtractor(llm_client)

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    async def run(
        self,
        user_id: UUID,
        content: str,
        content_type: ContentType,
        metadata: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        """Execute the full extraction pipeline.

        1. Chunk text
        2. Extract nodes per chunk
        3. Deduplicate and merge with existing graph nodes
        4. Extract edges
        5. Validate
        6. Commit to graph
        7. Create IngestEvent node
        """
        ingest_id = uuid.uuid4()
        user_id_str = str(user_id)
        meta = dict(metadata or {})
        meta["content_type"] = content_type.value

        log.info(
            "pipeline_started",
            ingest_id=str(ingest_id),
            user_id=user_id_str,
            content_type=content_type.value,
            content_length=len(content),
        )

        # 1. Chunk ---------------------------------------------------------
        chunks = chunk_text(content)
        if not chunks:
            log.warning("pipeline_empty_content", ingest_id=str(ingest_id))
            return ExtractionResult(ingest_id=ingest_id, metadata=meta)

        # 2. Extract nodes from each chunk ---------------------------------
        all_nodes: list[dict] = []
        for idx, chunk in enumerate(chunks):
            log.debug("extracting_chunk", chunk_index=idx, chunk_length=len(chunk))
            chunk_nodes = await self._node_extractor.extract_all(chunk)
            all_nodes.extend(chunk_nodes)

        # 3. Deduplicate locally -------------------------------------------
        all_nodes = deduplicate_nodes(all_nodes)

        # 3b. Merge with existing graph nodes (fulltext search) ------------
        all_nodes = await self._merge_with_existing(user_id_str, all_nodes)

        # 4. Extract edges -------------------------------------------------
        edges: list[dict] = []
        if all_nodes:
            edges = await self._edge_extractor.extract_edges(content, all_nodes)

        # 5. Validate edges ------------------------------------------------
        valid_ids = {n["temp_id"] for n in all_nodes if "temp_id" in n}
        edges = validate_relationships(edges, valid_ids)

        # 6. Commit to graph -----------------------------------------------
        committed_nodes, committed_edges = await self._commit(
            user_id_str, all_nodes, edges
        )

        # 7. Create IngestEvent node ----------------------------------------
        await self._create_ingest_event(
            user_id_str,
            ingest_id,
            committed_nodes,
            content_type,
            meta,
        )

        result = ExtractionResult(
            ingest_id=ingest_id,
            nodes=committed_nodes,
            edges=committed_edges,
            metadata=meta,
        )

        log.info(
            "pipeline_completed",
            ingest_id=str(ingest_id),
            nodes=len(committed_nodes),
            edges=len(committed_edges),
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _merge_with_existing(
        self,
        user_id: str,
        nodes: list[dict],
    ) -> list[dict]:
        """Try to match extracted nodes against existing graph nodes."""
        merged: list[dict] = []
        for node in nodes:
            search_term = node.get("name", node.get("description", ""))
            if not search_term:
                merged.append(node)
                continue
            try:
                existing = await self._repository.fulltext_search(
                    user_id, normalize_name(search_term), limit=3
                )
            except Exception:
                log.debug("fulltext_search_failed", search_term=search_term)
                merged.append(node)
                continue

            # If a high-confidence match exists, reuse its graph id.
            matched = False
            for hit in existing:
                if hit.get("score", 0) > 0.85:
                    node["graph_id"] = hit.get("id")
                    node["_merged"] = True
                    log.debug(
                        "node_merged_with_existing",
                        name=search_term,
                        graph_id=hit.get("id"),
                        score=hit.get("score"),
                    )
                    matched = True
                    break
            merged.append(node)
        return merged

    async def _commit(
        self,
        user_id: str,
        nodes: list[dict],
        edges: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """Write nodes and edges to the graph repository.

        Returns the committed nodes and edges with their real graph ids.
        """
        # Map temp_id -> real graph id for edge resolution.
        temp_to_real: dict[str, str] = {}
        committed_nodes: list[dict] = []

        for node in nodes:
            label_str = node.get("label", "Entity")
            label = _LABEL_MAP.get(label_str, NodeLabel.ENTITY)

            # If already merged with an existing node, skip creation.
            if node.get("_merged") and node.get("graph_id"):
                temp_to_real[node["temp_id"]] = node["graph_id"]
                committed_nodes.append(node)
                continue

            # Build properties dict, excluding internal keys.
            props = {
                k: v
                for k, v in node.items()
                if k not in {"temp_id", "label", "graph_id", "_merged"}
            }

            created = await self._repository.create_node(user_id, label, props)
            temp_to_real[node["temp_id"]] = created["id"]
            node["graph_id"] = created["id"]
            committed_nodes.append(node)

        committed_edges: list[dict] = []
        for edge in edges:
            source_real = temp_to_real.get(edge["source_id"])
            target_real = temp_to_real.get(edge["target_id"])
            if not source_real or not target_real:
                log.warning(
                    "edge_commit_skip_missing_id",
                    source_temp=edge["source_id"],
                    target_temp=edge["target_id"],
                )
                continue

            rel_type_str = edge.get("rel_type", RelationType.RELATED_TO.value)
            try:
                rel_type = RelationType(rel_type_str)
            except ValueError:
                rel_type = RelationType.RELATED_TO

            edge_props: dict[str, Any] = {}
            if edge.get("description"):
                edge_props["description"] = edge["description"]

            created_edge = await self._repository.create_edge(
                user_id, source_real, target_real, rel_type, edge_props
            )
            committed_edges.append(created_edge)

        return committed_nodes, committed_edges

    async def _create_ingest_event(
        self,
        user_id: str,
        ingest_id: UUID,
        committed_nodes: list[dict],
        content_type: ContentType,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Create an IngestEvent node and link it to all committed nodes."""
        event_props: dict[str, Any] = {
            "ingest_id": str(ingest_id),
            "source": content_type.value,
            "nodes_created": len(committed_nodes),
            "metadata": str(metadata),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

        event_node = await self._repository.create_node(
            user_id, NodeLabel.INGEST_EVENT, event_props
        )

        # Link each committed node to the IngestEvent via DERIVED_FROM.
        for node in committed_nodes:
            graph_id = node.get("graph_id")
            if graph_id:
                try:
                    await self._repository.create_edge(
                        user_id,
                        graph_id,
                        event_node["id"],
                        RelationType.DERIVED_FROM,
                    )
                except Exception:
                    log.warning(
                        "ingest_event_link_failed",
                        node_id=graph_id,
                        event_id=event_node["id"],
                    )

        return event_node
