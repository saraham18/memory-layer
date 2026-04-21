"""Build the LangGraph extraction workflow."""

from __future__ import annotations

import structlog
from langgraph.graph import END, StateGraph

from memory_layer.graph.repository import GraphRepository
from memory_layer.langgraph.edges import has_nodes, should_retry
from memory_layer.langgraph.nodes import _make_node_functions
from memory_layer.langgraph.states import ExtractionState
from memory_layer.llm.base import BaseLLMClient

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def build_extraction_graph(
    llm_client: BaseLLMClient,
    repository: GraphRepository,
) -> StateGraph:
    """Wire up the extraction workflow as a LangGraph :class:`StateGraph`.

    The graph has the following topology::

        START -> chunk -> extract_nodes --(has_nodes)--> extract_edges -> validate
                                         \\-- (no nodes) --> END                |
                                                                         should_retry
                                                                         /         \\
                                                                    retry          continue
                                                                  (chunk)          (commit)
                                                                                     |
                                                                                    END
    """
    fns = _make_node_functions(llm_client, repository)

    graph = StateGraph(ExtractionState)

    # Register nodes -------------------------------------------------------
    graph.add_node("chunk", fns["chunk_node"])
    graph.add_node("extract_nodes", fns["extract_nodes_node"])
    graph.add_node("extract_edges", fns["extract_edges_node"])
    graph.add_node("validate", fns["validate_node"])
    graph.add_node("commit", fns["commit_node"])

    # Set entry point ------------------------------------------------------
    graph.set_entry_point("chunk")

    # Unconditional edges --------------------------------------------------
    graph.add_edge("chunk", "extract_nodes")
    graph.add_edge("extract_edges", "validate")

    # Conditional: after extract_nodes, check if we have any nodes ----------
    graph.add_conditional_edges(
        "extract_nodes",
        has_nodes,
        {
            "extract_edges": "extract_edges",
            "end": END,
        },
    )

    # Conditional: after validate, decide retry or commit ------------------
    graph.add_conditional_edges(
        "validate",
        should_retry,
        {
            "retry": "chunk",
            "continue": "commit",
        },
    )

    # Commit leads to END --------------------------------------------------
    graph.add_edge("commit", END)

    log.info("extraction_graph_built")
    return graph
