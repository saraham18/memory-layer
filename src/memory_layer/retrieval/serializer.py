"""Serialise graph nodes and edges into natural-language context text."""

from __future__ import annotations

from typing import Any

from memory_layer.retrieval.context_window import ContextWindowManager, count_tokens


def serialize_node(node: dict[str, Any]) -> str:
    """Convert a single node dict into a natural-language sentence.

    The exact phrasing depends on the node label:

    * **FactualAssertion** — rendered as its ``content`` field.
    * **Entity** — ``"<name> is a <entity_type>."``
    * **UserGoal** — ``"User goal: <description>."``
    * **Concept** — ``"Concept: <name>."``
    * Fallback — ``"<label>: <name or id>."``
    """
    label = node.get("label", "")
    name = node.get("name", "")
    content = node.get("content", "")
    entity_type = node.get("entity_type", "")
    description = node.get("description", "")
    confidence = node.get("confidence")

    if label == "FactualAssertion" and content:
        sentence = content.rstrip(".")
        if confidence is not None:
            sentence += f" (confidence: {confidence})"
        return sentence + "."

    if label == "Entity" and name:
        base = f"{name} is a {entity_type}." if entity_type else f"{name} (entity)."
        return base

    if label == "UserGoal" and description:
        return f"User goal: {description.rstrip('.')}."

    if label == "Concept" and name:
        return f"Concept: {name}."

    # Fallback.
    display = name or content or description or node.get("id", "unknown")
    if label:
        return f"{label}: {display}."
    return str(display) + "."


def serialize_subgraph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> str:
    """Serialize a full subgraph (nodes + edges) as human-readable text.

    Parameters
    ----------
    nodes:
        Node dicts as returned by the traversal layer.
    edges:
        Edge dicts connecting the nodes.

    Returns
    -------
    str:
        A readable multi-line string describing the subgraph.
    """
    lines: list[str] = []

    # Build a quick id -> display-name lookup.
    id_to_name: dict[str, str] = {}
    for node in nodes:
        nid = str(node.get("id", ""))
        display = node.get("name") or node.get("content", nid)
        # Truncate long content for edge descriptions.
        if len(display) > 80:
            display = display[:77] + "..."
        id_to_name[nid] = display

    # Nodes section.
    if nodes:
        lines.append("Facts and entities:")
        for node in nodes:
            lines.append(f"- {serialize_node(node)}")

    # Edges section.
    if edges:
        lines.append("")
        lines.append("Relationships:")
        for edge in edges:
            src = id_to_name.get(str(edge.get("source_id", "")), "?")
            tgt = id_to_name.get(str(edge.get("target_id", "")), "?")
            rel = edge.get("rel_type") or edge.get("relationship", "RELATED_TO")
            lines.append(f"- {src} --[{rel}]--> {tgt}")

    return "\n".join(lines)


def build_master_context(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    max_tokens: int = 4000,
) -> tuple[str, int]:
    """Build a natural-language context string within a token budget.

    Nodes are serialised in order (assumed pre-ranked by relevance).  Each
    serialised sentence is added until the budget is exhausted.  Edges
    between included nodes are appended at the end if space permits.

    Parameters
    ----------
    nodes:
        Pre-ranked node dicts.
    edges:
        Edge dicts for the subgraph.
    max_tokens:
        Maximum token budget for the output.

    Returns
    -------
    tuple[str, int]:
        ``(context_text, token_count)``
    """
    manager = ContextWindowManager(max_tokens=max_tokens)

    # Header.
    header = "Relevant knowledge from the memory graph:"
    manager.add(header)

    # Build set of included node ids for edge filtering.
    included_ids: set[str] = set()

    # Add node sentences in rank order.
    for node in nodes:
        sentence = f"- {serialize_node(node)}"
        if manager.fits(sentence):
            manager.add(sentence)
            included_ids.add(str(node.get("id", "")))
        else:
            # Budget exhausted for nodes.
            break

    # Filter edges to only those connecting included nodes.
    relevant_edges = [
        e for e in edges
        if str(e.get("source_id", "")) in included_ids
        and str(e.get("target_id", "")) in included_ids
    ]

    if relevant_edges:
        # Build an id -> name lookup from included nodes.
        id_to_name: dict[str, str] = {}
        for node in nodes:
            nid = str(node.get("id", ""))
            if nid in included_ids:
                display = node.get("name") or node.get("content", nid)
                if len(display) > 80:
                    display = display[:77] + "..."
                id_to_name[nid] = display

        edge_header = "\nRelationships:"
        if manager.fits(edge_header):
            manager.add(edge_header)
            for edge in relevant_edges:
                src = id_to_name.get(str(edge.get("source_id", "")), "?")
                tgt = id_to_name.get(str(edge.get("target_id", "")), "?")
                rel = edge.get("rel_type") or edge.get("relationship", "RELATED_TO")
                line = f"- {src} --[{rel}]--> {tgt}"
                if not manager.add(line):
                    break

    context_text = manager.text
    token_count = count_tokens(context_text)
    return context_text, token_count
