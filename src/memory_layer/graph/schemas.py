"""Node labels, relationship types, and property constraints for the knowledge graph."""

from __future__ import annotations

from enum import StrEnum


# ---------------------------------------------------------------------------
# Node labels
# ---------------------------------------------------------------------------

class NodeLabel(StrEnum):
    """Every node in the graph is tagged with exactly one of these labels."""

    USER = "User"
    API_KEY = "APIKey"
    ENTITY = "Entity"
    USER_GOAL = "UserGoal"
    FACTUAL_ASSERTION = "FactualAssertion"
    CONCEPT = "Concept"
    INGEST_EVENT = "IngestEvent"


# ---------------------------------------------------------------------------
# Relationship types
# ---------------------------------------------------------------------------

class RelationType(StrEnum):
    """Typed edges between nodes."""

    OWNS_KEY = "OWNS_KEY"
    DEPENDS_ON = "DEPENDS_ON"
    CONTRADICTS = "CONTRADICTS"
    SUPPORTS = "SUPPORTS"
    RELATED_TO = "RELATED_TO"
    HAS_GOAL = "HAS_GOAL"
    ASSERTS = "ASSERTS"
    DERIVED_FROM = "DERIVED_FROM"
    PART_OF = "PART_OF"
    SUPERSEDES = "SUPERSEDES"
    INVOLVES = "INVOLVES"
    REQUIRES = "REQUIRES"


# ---------------------------------------------------------------------------
# Required properties per label
# ---------------------------------------------------------------------------

# Every node MUST have at least these properties.
REQUIRED_PROPERTIES: dict[NodeLabel, frozenset[str]] = {
    NodeLabel.USER: frozenset({"id", "user_id", "created_at"}),
    NodeLabel.API_KEY: frozenset({"id", "user_id", "key_hash", "created_at"}),
    NodeLabel.ENTITY: frozenset({"id", "user_id", "name", "entity_type", "created_at"}),
    NodeLabel.USER_GOAL: frozenset({"id", "user_id", "description", "created_at"}),
    NodeLabel.FACTUAL_ASSERTION: frozenset({"id", "user_id", "content", "confidence", "created_at"}),
    NodeLabel.CONCEPT: frozenset({"id", "user_id", "name", "created_at"}),
    NodeLabel.INGEST_EVENT: frozenset({"id", "user_id", "source", "created_at"}),
}


# Fulltext-searchable properties (label -> property names).
FULLTEXT_PROPERTIES: dict[NodeLabel, list[str]] = {
    NodeLabel.ENTITY: ["name"],
    NodeLabel.CONCEPT: ["name"],
    NodeLabel.FACTUAL_ASSERTION: ["content"],
}

# Name of the composite fulltext index used for search.
FULLTEXT_INDEX_NAME: str = "memory_fulltext_search"
