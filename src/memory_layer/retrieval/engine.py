"""Retrieval engine — GraphRAG pipeline from user query to master context."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from memory_layer.graph.repository import GraphRepository
from memory_layer.llm.base import BaseLLMClient
from memory_layer.models.query import (
    ExplainResponse,
    QueryResponse,
    Subgraph,
    SubgraphEdge,
    SubgraphNode,
)
from memory_layer.retrieval.context_window import count_tokens
from memory_layer.retrieval.ranking import rank_nodes, select_top_n
from memory_layer.retrieval.serializer import build_master_context
from memory_layer.retrieval.traversal import GraphTraverser

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_SEED_EXTRACTION_SYSTEM = (
    "You are a search-term extractor.  Given a user question, identify the key "
    "noun phrases, named entities, and concepts that should be used to search a "
    "knowledge graph.  Respond ONLY with valid JSON."
)

_SEED_EXTRACTION_PROMPT = """\
Extract search terms from the following user query.  Return a JSON object:
{{
    "terms": ["term1", "term2", ...]
}}

Only include the most important nouns, names, and concepts (up to 8 terms).

User query:
\"\"\"{query}\"\"\"
"""


class RetrievalEngine:
    """End-to-end retrieval pipeline: query -> seed -> traverse -> rank -> serialise.

    Parameters
    ----------
    llm_client:
        Used for seed-term extraction from the user query.
    repository:
        Tenant-scoped graph repository.
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        repository: GraphRepository,
    ) -> None:
        self._llm = llm_client
        self._repo = repository
        self._traverser = GraphTraverser(repository)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(
        self,
        user_id: UUID,
        query: str,
        max_hops: int = 3,
        max_tokens: int = 4000,
    ) -> QueryResponse:
        """Run the full retrieval pipeline and return a :class:`QueryResponse`.

        Steps
        -----
        1. Extract seed terms from *query* via LLM.
        2. Find seed nodes via fulltext search.
        3. BFS-traverse from seeds up to *max_hops*.
        4. Rank and select top nodes.
        5. Gather edges between selected nodes.
        6. Serialise as master context within the token budget.
        7. Build and return ``QueryResponse``.
        """
        uid = str(user_id)

        # Step 1 — seed term extraction.
        seed_terms = await self._extract_seed_terms(query)
        log.info("seed_terms_extracted", user_id=uid, terms=seed_terms)

        # Step 2 — find seed nodes.
        seed_nodes = await self._traverser.get_seed_nodes(user_id, seed_terms)
        seed_ids = [UUID(n["id"]) for n in seed_nodes if n.get("id")]

        # Step 3 — BFS traverse.
        traversed = await self._traverser.bfs_traverse(user_id, seed_ids, max_hops=max_hops)

        # Step 4 — rank and select.
        top_nodes = select_top_n(traversed, n=50)

        # Step 5 — gather edges.
        edges = await self._collect_edges(uid, top_nodes)

        # Step 6 — serialise.
        master_context, token_count = build_master_context(top_nodes, edges, max_tokens)

        # Step 7 — build response.
        subgraph = self._build_subgraph(top_nodes, edges)

        return QueryResponse(
            master_context=master_context,
            subgraph=subgraph,
            seed_terms=seed_terms,
            token_count=token_count,
        )

    async def query_explain(
        self,
        user_id: UUID,
        query: str,
        max_hops: int = 3,
        max_tokens: int = 4000,
    ) -> ExplainResponse:
        """Same as :meth:`query` but includes traversal trace and scoring details."""
        uid = str(user_id)

        # Step 1.
        seed_terms = await self._extract_seed_terms(query)
        log.info("seed_terms_extracted", user_id=uid, terms=seed_terms, explain=True)

        # Step 2.
        seed_nodes = await self._traverser.get_seed_nodes(user_id, seed_terms)
        seed_ids = [UUID(n["id"]) for n in seed_nodes if n.get("id")]

        traversal_trace: list[dict[str, Any]] = [
            {
                "step": "seed_nodes",
                "count": len(seed_nodes),
                "ids": [n.get("id") for n in seed_nodes],
            }
        ]

        # Step 3.
        traversed = await self._traverser.bfs_traverse(user_id, seed_ids, max_hops=max_hops)
        traversal_trace.append({
            "step": "bfs_traverse",
            "nodes_discovered": len(traversed),
            "max_hops": max_hops,
        })

        # Step 4.
        ranked = rank_nodes(list(traversed))
        top_nodes = ranked[:50]

        scoring_details: list[dict[str, Any]] = [
            {
                "node_id": n.get("id"),
                "name": n.get("name") or n.get("content", "")[:60],
                "hop_distance": n.get("hop_distance", 0),
                "confidence": n.get("confidence", 0.5),
                "score": n.get("_score", 0.0),
            }
            for n in top_nodes
        ]

        # Step 5.
        edges = await self._collect_edges(uid, top_nodes)

        # Step 6.
        master_context, token_count = build_master_context(top_nodes, edges, max_tokens)

        # Step 7.
        subgraph = self._build_subgraph(top_nodes, edges)

        return ExplainResponse(
            master_context=master_context,
            subgraph=subgraph,
            seed_terms=seed_terms,
            token_count=token_count,
            traversal_trace=traversal_trace,
            scoring_details=scoring_details,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _extract_seed_terms(self, query: str) -> list[str]:
        """Ask the LLM to extract search terms from the user's query."""
        prompt = _SEED_EXTRACTION_PROMPT.format(query=query)
        try:
            result = await self._llm.complete_json(
                prompt,
                system=_SEED_EXTRACTION_SYSTEM,
                temperature=0.0,
                max_tokens=256,
            )
            terms = result.get("terms", [])
            if isinstance(terms, list):
                return [str(t) for t in terms if t]
        except Exception:
            log.exception("seed_term_extraction_failed")

        # Fallback: naive whitespace split.
        return [w for w in query.split() if len(w) > 2]

    async def _collect_edges(
        self,
        user_id: str,
        nodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Gather all edges between the given nodes."""
        node_ids = {str(n.get("id", "")) for n in nodes}
        seen: set[tuple[str, str, str]] = set()
        edges: list[dict[str, Any]] = []

        for nid in node_ids:
            if not nid:
                continue
            node_edges = await self._repo.get_edges(user_id, nid)
            for edge in node_edges:
                src = edge.get("source_id", "")
                tgt = edge.get("target_id", "")
                rel = edge.get("rel_type", "")
                key = (src, tgt, rel)
                if key in seen:
                    continue
                # Only include edges where both endpoints are in the selected set.
                if src in node_ids and tgt in node_ids:
                    seen.add(key)
                    edges.append(edge)

        return edges

    @staticmethod
    def _build_subgraph(
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> Subgraph:
        """Convert raw dicts into the typed Subgraph model."""
        sg_nodes: list[SubgraphNode] = []
        for n in nodes:
            try:
                sg_nodes.append(SubgraphNode(
                    id=n["id"],
                    label=n.get("label", "Entity"),
                    name=n.get("name") or n.get("content", "")[:100],
                    properties={
                        k: v for k, v in n.items()
                        if k not in {"id", "label", "name", "confidence", "hop_distance", "_score"}
                    },
                    confidence=float(n.get("confidence", 0.5)),
                    hop_distance=int(n.get("hop_distance", 0)),
                ))
            except (KeyError, ValueError):
                log.warning("skip_invalid_node", node=n)

        sg_edges: list[SubgraphEdge] = []
        for e in edges:
            try:
                props = e.get("properties", {})
                sg_edges.append(SubgraphEdge(
                    source_id=e["source_id"],
                    target_id=e["target_id"],
                    relationship=e.get("rel_type") or e.get("relationship", "RELATED_TO"),
                    confidence=float(props.get("confidence", 1.0)),
                ))
            except (KeyError, ValueError):
                log.warning("skip_invalid_edge", edge=e)

        return Subgraph(nodes=sg_nodes, edges=sg_edges)
