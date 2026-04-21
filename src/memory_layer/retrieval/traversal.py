"""Graph traversal utilities for the retrieval engine."""

from __future__ import annotations

from collections import deque
from typing import Any
from uuid import UUID

import structlog

from memory_layer.graph.repository import GraphRepository

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class GraphTraverser:
    """Breadth-first traversal and seed-node discovery for retrieval.

    Parameters
    ----------
    repository:
        The tenant-scoped graph repository.
    """

    def __init__(self, repository: GraphRepository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def bfs_traverse(
        self,
        user_id: UUID,
        seed_node_ids: list[UUID],
        max_hops: int = 3,
    ) -> list[dict[str, Any]]:
        """BFS from *seed_node_ids*, returning nodes annotated with hop distance.

        Each returned dict contains the node's own properties plus an
        additional ``hop_distance`` key indicating how many edges away it is
        from the nearest seed.

        Parameters
        ----------
        user_id:
            Tenant scope.
        seed_node_ids:
            Starting nodes for the traversal.
        max_hops:
            Maximum number of hops to explore from any seed.

        Returns
        -------
        list[dict]:
            Node dicts augmented with ``hop_distance``.
        """
        uid = str(user_id)

        # node_id -> minimum hop distance from any seed
        visited: dict[str, int] = {}
        # node_id -> full node dict
        node_data: dict[str, dict[str, Any]] = {}

        # BFS queue: (node_id, current_hop)
        queue: deque[tuple[str, int]] = deque()

        # Initialise with seed nodes at distance 0.
        for sid in seed_node_ids:
            sid_str = str(sid)
            if sid_str in visited:
                continue
            node = await self._repo.get_node(uid, sid_str)
            if node is None:
                log.debug("seed_node_missing", user_id=uid, node_id=sid_str)
                continue
            visited[sid_str] = 0
            node_data[sid_str] = node
            queue.append((sid_str, 0))

        # BFS loop.
        while queue:
            current_id, current_hop = queue.popleft()

            if current_hop >= max_hops:
                continue

            neighbors = await self._repo.get_neighbors(uid, current_id, max_hops=1)
            for neighbor in neighbors:
                nid = neighbor.get("id", "")
                if not nid:
                    continue
                next_hop = current_hop + 1
                if nid not in visited or visited[nid] > next_hop:
                    visited[nid] = next_hop
                    node_data[nid] = neighbor
                    queue.append((nid, next_hop))

        # Build result list.
        results: list[dict[str, Any]] = []
        for nid, hop in visited.items():
            entry = dict(node_data[nid])
            entry["hop_distance"] = hop
            results.append(entry)

        log.info(
            "bfs_traversal_complete",
            user_id=uid,
            seeds=len(seed_node_ids),
            nodes_discovered=len(results),
            max_hops=max_hops,
        )
        return results

    async def get_seed_nodes(
        self,
        user_id: UUID,
        terms: list[str],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fulltext-search for each term and return deduplicated top nodes.

        Parameters
        ----------
        user_id:
            Tenant scope.
        terms:
            Search terms extracted from the user query.
        limit:
            Maximum number of seed nodes to return.

        Returns
        -------
        list[dict]:
            Matched nodes, deduplicated and capped at *limit*.
        """
        uid = str(user_id)
        seen_ids: set[str] = set()
        results: list[dict[str, Any]] = []

        for term in terms:
            term = term.strip()
            if not term:
                continue
            matches = await self._repo.fulltext_search(uid, term, limit=limit)
            for match in matches:
                nid = match.get("id", "")
                if nid and nid not in seen_ids:
                    seen_ids.add(nid)
                    results.append(match)

        # Sort by search score (descending) and cap at limit.
        results.sort(key=lambda n: float(n.get("score", 0.0)), reverse=True)
        top = results[:limit]

        log.info(
            "seed_nodes_found",
            user_id=uid,
            terms=terms,
            total_matches=len(results),
            returned=len(top),
        )
        return top
