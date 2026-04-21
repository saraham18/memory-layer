"""Scoring and ranking utilities for retrieved graph nodes."""

from __future__ import annotations

from typing import Any


def score_node(node: dict[str, Any], hop_distance: int) -> float:
    """Compute a relevance score for a single node.

    Formula
    -------
    ``(1 / (hop_distance + 1)) * node_confidence``

    Nodes closer to the seed and with higher confidence score higher.

    Parameters
    ----------
    node:
        A node dict, expected to have a ``confidence`` key (defaults to 0.5).
    hop_distance:
        Number of hops from the nearest seed node.

    Returns
    -------
    float:
        The computed relevance score.
    """
    confidence = float(node.get("confidence", 0.5))
    return (1.0 / (hop_distance + 1)) * confidence


def rank_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score every node and return the list sorted by score descending.

    Each node dict is expected to carry a ``hop_distance`` key (as produced
    by :class:`~memory_layer.retrieval.traversal.GraphTraverser`).  A
    ``_score`` key is added to each dict so downstream consumers can inspect
    the computed value.

    Parameters
    ----------
    nodes:
        Node dicts with ``hop_distance`` and ``confidence``.

    Returns
    -------
    list[dict]:
        The same dicts, augmented with ``_score`` and sorted descending.
    """
    for node in nodes:
        hop = int(node.get("hop_distance", 0))
        node["_score"] = score_node(node, hop)

    return sorted(nodes, key=lambda n: n["_score"], reverse=True)


def select_top_n(nodes: list[dict[str, Any]], n: int = 50) -> list[dict[str, Any]]:
    """Rank nodes and return the top *n*.

    Parameters
    ----------
    nodes:
        Node dicts with ``hop_distance`` and ``confidence``.
    n:
        Maximum number of nodes to return.

    Returns
    -------
    list[dict]:
        Top-*n* nodes ranked by score.
    """
    ranked = rank_nodes(nodes)
    return ranked[:n]
