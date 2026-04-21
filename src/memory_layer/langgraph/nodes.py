"""LangGraph node functions for the extraction workflow."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from memory_layer.extraction.edge_extractor import EdgeExtractor
from memory_layer.extraction.node_extractor import NodeExtractor
from memory_layer.extraction.spacy_config import chunk_text
from memory_layer.extraction.validators import (
    deduplicate_nodes,
    validate_relationships,
)
from memory_layer.graph.repository import GraphRepository
from memory_layer.graph.schemas import NodeLabel, RelationType
from memory_layer.langgraph.states import ExtractionState
from memory_layer.llm.base import BaseLLMClient

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Mapping from extraction label strings to graph NodeLabel enum members.
_LABEL_MAP: dict[str, NodeLabel] = {
    "Entity": NodeLabel.ENTITY,
    "UserGoal": NodeLabel.USER_GOAL,
    "FactualAssertion": NodeLabel.FACTUAL_ASSERTION,
    "Concept": NodeLabel.CONCEPT,
}


def _make_node_functions(
    llm_client: BaseLLMClient,
    repository: GraphRepository,
) -> dict[str, Any]:
    """Create and return a dictionary of LangGraph node functions.

    The returned functions close over *llm_client* and *repository* so they
    can be registered directly in a :class:`StateGraph`.
    """
    node_extractor = NodeExtractor(llm_client)
    edge_extractor = EdgeExtractor(llm_client)

    # ------------------------------------------------------------------
    # 1. chunk_node
    # ------------------------------------------------------------------

    async def chunk_node(state: ExtractionState) -> ExtractionState:
        """Split the input text into processable chunks."""
        text = state.get("text", "")
        errors: list[str] = list(state.get("errors", []))

        if not text.strip():
            errors.append("Empty input text")
            return {**state, "chunks": [], "errors": errors}

        try:
            chunks = chunk_text(text)
        except Exception as exc:
            errors.append(f"Chunking failed: {exc}")
            chunks = [text]  # Fallback: treat entire text as one chunk.

        log.info("chunk_node_completed", num_chunks=len(chunks))
        return {
            **state,
            "chunks": chunks,
            "errors": errors,
            "ingest_id": state.get("ingest_id", str(uuid.uuid4())),
        }

    # ------------------------------------------------------------------
    # 2. extract_nodes_node
    # ------------------------------------------------------------------

    async def extract_nodes_node(state: ExtractionState) -> ExtractionState:
        """Extract entities, goals, and assertions from each chunk."""
        chunks: list[str] = state.get("chunks", [])
        errors: list[str] = list(state.get("errors", []))
        all_nodes: list[dict] = list(state.get("nodes", []))

        for idx, chunk in enumerate(chunks):
            try:
                chunk_nodes = await node_extractor.extract_all(chunk)
                all_nodes.extend(chunk_nodes)
            except Exception as exc:
                errors.append(f"Node extraction failed for chunk {idx}: {exc}")
                log.warning(
                    "extract_nodes_chunk_failed",
                    chunk_index=idx,
                    error=str(exc),
                )

        all_nodes = deduplicate_nodes(all_nodes)
        log.info("extract_nodes_node_completed", total_nodes=len(all_nodes))
        return {**state, "nodes": all_nodes, "errors": errors}

    # ------------------------------------------------------------------
    # 3. extract_edges_node
    # ------------------------------------------------------------------

    async def extract_edges_node(state: ExtractionState) -> ExtractionState:
        """Extract edges given the extracted nodes."""
        nodes: list[dict] = state.get("nodes", [])
        errors: list[str] = list(state.get("errors", []))
        text = state.get("text", "")

        edges: list[dict] = []
        if nodes:
            try:
                edges = await edge_extractor.extract_edges(text, nodes)
            except Exception as exc:
                errors.append(f"Edge extraction failed: {exc}")
                log.warning("extract_edges_failed", error=str(exc))

        log.info("extract_edges_node_completed", total_edges=len(edges))
        return {**state, "edges": edges, "errors": errors}

    # ------------------------------------------------------------------
    # 4. validate_node
    # ------------------------------------------------------------------

    async def validate_node(state: ExtractionState) -> ExtractionState:
        """Validate extracted nodes and edges."""
        nodes: list[dict] = state.get("nodes", [])
        edges: list[dict] = state.get("edges", [])
        errors: list[str] = list(state.get("errors", []))

        valid_ids = {n["temp_id"] for n in nodes if "temp_id" in n}
        validated_edges = validate_relationships(edges, valid_ids)

        if len(validated_edges) < len(edges):
            dropped = len(edges) - len(validated_edges)
            errors.append(f"Validation dropped {dropped} invalid edges")

        log.info(
            "validate_node_completed",
            valid_nodes=len(nodes),
            valid_edges=len(validated_edges),
        )
        return {
            **state,
            "edges": validated_edges,
            "validated": True,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # 5. commit_node
    # ------------------------------------------------------------------

    async def commit_node(state: ExtractionState) -> ExtractionState:
        """Commit validated nodes and edges to the graph repository."""
        nodes: list[dict] = state.get("nodes", [])
        edges: list[dict] = state.get("edges", [])
        user_id: str = state.get("user_id", "")
        errors: list[str] = list(state.get("errors", []))

        if not user_id:
            errors.append("Missing user_id — cannot commit to graph")
            return {**state, "committed": False, "errors": errors}

        temp_to_real: dict[str, str] = {}
        committed_nodes: list[dict] = []

        for node in nodes:
            label_str = node.get("label", "Entity")
            label = _LABEL_MAP.get(label_str, NodeLabel.ENTITY)
            props = {
                k: v
                for k, v in node.items()
                if k not in {"temp_id", "label", "graph_id", "_merged"}
            }
            try:
                created = await repository.create_node(user_id, label, props)
                temp_to_real[node["temp_id"]] = created["id"]
                node["graph_id"] = created["id"]
                committed_nodes.append(node)
            except Exception as exc:
                errors.append(f"Failed to create node: {exc}")
                log.warning("commit_node_failed", error=str(exc))

        committed_edges: list[dict] = []
        for edge in edges:
            source_real = temp_to_real.get(edge["source_id"])
            target_real = temp_to_real.get(edge["target_id"])
            if not source_real or not target_real:
                continue
            rel_type_str = edge.get("rel_type", RelationType.RELATED_TO.value)
            try:
                rel_type = RelationType(rel_type_str)
            except ValueError:
                rel_type = RelationType.RELATED_TO
            edge_props: dict[str, Any] = {}
            if edge.get("description"):
                edge_props["description"] = edge["description"]
            try:
                created_edge = await repository.create_edge(
                    user_id, source_real, target_real, rel_type, edge_props
                )
                committed_edges.append(created_edge)
            except Exception as exc:
                errors.append(f"Failed to create edge: {exc}")
                log.warning("commit_edge_failed", error=str(exc))

        log.info(
            "commit_node_completed",
            nodes_committed=len(committed_nodes),
            edges_committed=len(committed_edges),
        )
        return {
            **state,
            "nodes": committed_nodes,
            "edges": committed_edges,
            "committed": True,
            "errors": errors,
        }

    return {
        "chunk_node": chunk_node,
        "extract_nodes_node": extract_nodes_node,
        "extract_edges_node": extract_edges_node,
        "validate_node": validate_node,
        "commit_node": commit_node,
    }
