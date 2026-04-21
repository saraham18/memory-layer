"""Output validation and normalisation helpers for extracted data."""

from __future__ import annotations

import re

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------


def normalize_name(name: str) -> str:
    """Lower-case, strip, and collapse consecutive whitespace."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _similarity(a: str, b: str) -> float:
    """Simple character-bigram Dice coefficient for fuzzy matching."""
    if a == b:
        return 1.0
    if len(a) < 2 or len(b) < 2:
        return 0.0

    def _bigrams(s: str) -> dict[str, int]:
        bg: dict[str, int] = {}
        for i in range(len(s) - 1):
            pair = s[i : i + 2]
            bg[pair] = bg.get(pair, 0) + 1
        return bg

    bg_a = _bigrams(a)
    bg_b = _bigrams(b)
    overlap = 0
    for pair, count in bg_a.items():
        overlap += min(count, bg_b.get(pair, 0))
    total = sum(bg_a.values()) + sum(bg_b.values())
    if total == 0:
        return 0.0
    return (2.0 * overlap) / total


# ---------------------------------------------------------------------------
# Entity validation
# ---------------------------------------------------------------------------

_REQUIRED_ENTITY_KEYS: set[str] = {"name", "entity_type"}


def validate_entities(data: list[dict]) -> list[dict]:
    """Validate and normalise a list of extracted entity dicts.

    Each entity must contain at least ``name`` and ``entity_type``.
    Names are normalised; invalid entries are silently dropped.
    """
    valid: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            log.warning("entity_invalid_type", item=item)
            continue
        if not _REQUIRED_ENTITY_KEYS.issubset(item.keys()):
            log.warning("entity_missing_keys", item=item)
            continue
        name = item.get("name", "")
        if not isinstance(name, str) or not name.strip():
            log.warning("entity_empty_name", item=item)
            continue

        item["name"] = normalize_name(name)
        item.setdefault("description", "")
        valid.append(item)
    return valid


# ---------------------------------------------------------------------------
# Relationship / edge validation
# ---------------------------------------------------------------------------


def validate_relationships(
    data: list[dict],
    valid_node_ids: set[str],
) -> list[dict]:
    """Validate edges, ensuring both endpoints reference known node ids."""
    valid: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            log.warning("edge_invalid_type", item=item)
            continue
        src = item.get("source_id")
        tgt = item.get("target_id")
        if src not in valid_node_ids or tgt not in valid_node_ids:
            log.warning(
                "edge_dangling_reference",
                source_id=src,
                target_id=tgt,
            )
            continue
        if not item.get("rel_type"):
            log.warning("edge_missing_rel_type", item=item)
            continue
        valid.append(item)
    return valid


# ---------------------------------------------------------------------------
# Node deduplication
# ---------------------------------------------------------------------------

_SIMILARITY_THRESHOLD: float = 0.85


def deduplicate_nodes(
    nodes: list[dict],
    threshold: float = _SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Merge nodes whose normalised names are similar above *threshold*.

    When two nodes are deemed duplicates the **first** encountered node is
    kept.  Its description is extended with any new information from the
    duplicate.
    """
    unique: list[dict] = []
    seen_names: list[str] = []

    for node in nodes:
        name = normalize_name(node.get("name", "") or node.get("description", ""))
        merged = False
        for idx, existing_name in enumerate(seen_names):
            if _similarity(name, existing_name) >= threshold:
                # Merge description if the duplicate adds information.
                dup_desc = node.get("description", "")
                existing_desc = unique[idx].get("description", "")
                if dup_desc and dup_desc not in existing_desc:
                    unique[idx]["description"] = (
                        f"{existing_desc} {dup_desc}".strip()
                    )
                merged = True
                log.debug(
                    "node_deduplicated",
                    kept=existing_name,
                    dropped=name,
                )
                break
        if not merged:
            unique.append(node)
            seen_names.append(name)

    return unique
