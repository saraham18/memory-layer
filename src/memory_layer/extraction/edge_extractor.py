"""Relationship / edge extraction via LLM."""

from __future__ import annotations

import json

import structlog

from memory_layer.extraction.prompts import RELATIONSHIP_EXTRACTION_PROMPT
from memory_layer.graph.schemas import RelationType
from memory_layer.llm.base import BaseLLMClient

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Build a lookup from upper-case name to enum member for fast mapping.
_REL_TYPE_LOOKUP: dict[str, RelationType] = {rt.value: rt for rt in RelationType}


def _map_rel_type(raw: str) -> RelationType | None:
    """Attempt to map a raw relationship string to a ``RelationType``."""
    normalised = raw.strip().upper().replace(" ", "_")
    return _REL_TYPE_LOOKUP.get(normalised)


class EdgeExtractor:
    """Extracts relationships between already-identified nodes using an LLM."""

    def __init__(self, llm_client: BaseLLMClient) -> None:
        self._llm = llm_client

    async def extract_edges(
        self,
        text: str,
        nodes: list[dict],
    ) -> list[dict]:
        """Given *text* and extracted *nodes*, identify relationships.

        Each returned dict contains ``source_id``, ``target_id``,
        ``rel_type`` (a :class:`RelationType` value string), and an optional
        ``description``.
        """
        if not nodes:
            return []

        # Build a concise JSON summary of nodes for the prompt.
        nodes_summary = [
            {
                "temp_id": n.get("temp_id", ""),
                "name": n.get("name", n.get("description", "")),
                "label": n.get("label", ""),
            }
            for n in nodes
        ]

        prompt = RELATIONSHIP_EXTRACTION_PROMPT.format(
            text=text,
            nodes_json=json.dumps(nodes_summary, indent=2),
        )

        result = await self._llm.complete_json(
            prompt=prompt,
            system="You are a precise relationship extraction engine. Return valid JSON only.",
            temperature=0.0,
        )

        raw_edges = result.get("relationships", [])
        edges: list[dict] = []

        valid_temp_ids = {n.get("temp_id") for n in nodes if n.get("temp_id")}

        for item in raw_edges:
            if not isinstance(item, dict):
                continue

            source_id = item.get("source_id")
            target_id = item.get("target_id")
            raw_rel = item.get("rel_type", "")

            if source_id not in valid_temp_ids or target_id not in valid_temp_ids:
                log.warning(
                    "edge_unknown_temp_id",
                    source_id=source_id,
                    target_id=target_id,
                )
                continue

            rel_type = _map_rel_type(raw_rel)
            if rel_type is None:
                log.warning("edge_unknown_rel_type", raw_rel_type=raw_rel)
                # Fall back to RELATED_TO for unrecognised types.
                rel_type = RelationType.RELATED_TO

            edges.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "rel_type": rel_type.value,
                    "description": item.get("description", ""),
                }
            )

        log.info("edges_extracted", count=len(edges))
        return edges
