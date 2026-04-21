"""Conditional edge functions for the LangGraph extraction workflow."""

from __future__ import annotations

from memory_layer.langgraph.states import ExtractionState

_MAX_RETRIES: int = 3


def should_retry(state: ExtractionState) -> str:
    """Decide whether to retry after errors.

    Returns ``"retry"`` if there are errors and the retry budget has not been
    exhausted, otherwise ``"continue"``.
    """
    errors = state.get("errors", [])
    retries = state.get("retries", 0)

    if errors and retries < _MAX_RETRIES:
        return "retry"
    return "continue"


def has_nodes(state: ExtractionState) -> str:
    """Decide whether to proceed to edge extraction.

    Returns ``"extract_edges"`` if at least one node was extracted,
    otherwise ``"end"``.
    """
    nodes = state.get("nodes", [])

    if nodes:
        return "extract_edges"
    return "end"
