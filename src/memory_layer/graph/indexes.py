"""Index and constraint creation for the Neo4j knowledge graph."""

from __future__ import annotations

import structlog

from memory_layer.graph.driver import GraphDriver
from memory_layer.graph.schemas import (
    FULLTEXT_INDEX_NAME,
    FULLTEXT_PROPERTIES,
    NodeLabel,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def ensure_indexes(driver: GraphDriver) -> None:
    """Create all required constraints and indexes if they do not already exist.

    This function is idempotent and safe to call on every application start.

    It creates:
    * A **uniqueness constraint** on ``id`` for every :class:`NodeLabel`.
    * A **range index** on ``user_id`` for every :class:`NodeLabel` to
      support fast tenant-scoped lookups.
    * A **fulltext index** across searchable properties defined in
      :data:`~memory_layer.graph.schemas.FULLTEXT_PROPERTIES`.
    """
    async with driver.session() as session:
        # -- Uniqueness constraints on `id` ----------------------------------
        for label in NodeLabel:
            constraint_name = f"uniq_{label.value.lower()}_id"
            cypher = (
                f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                f"FOR (n:{label.value}) REQUIRE n.id IS UNIQUE"
            )
            await session.run(cypher)
            log.debug("ensure_constraint", constraint=constraint_name)

        # -- Range indexes on `user_id` --------------------------------------
        for label in NodeLabel:
            index_name = f"idx_{label.value.lower()}_user_id"
            cypher = (
                f"CREATE INDEX {index_name} IF NOT EXISTS "
                f"FOR (n:{label.value}) ON (n.user_id)"
            )
            await session.run(cypher)
            log.debug("ensure_index", index=index_name)

        # -- Fulltext index for search ----------------------------------------
        # Build a single composite fulltext index across multiple labels/props.
        # Neo4j fulltext syntax:
        #   CREATE FULLTEXT INDEX name IF NOT EXISTS
        #   FOR (n:Label1|Label2) ON EACH [n.prop1, n.prop2]
        labels_part = "|".join(label.value for label in FULLTEXT_PROPERTIES)
        props: list[str] = []
        for prop_list in FULLTEXT_PROPERTIES.values():
            for prop in prop_list:
                qualified = f"n.{prop}"
                if qualified not in props:
                    props.append(qualified)
        props_part = ", ".join(props)

        fulltext_cypher = (
            f"CREATE FULLTEXT INDEX {FULLTEXT_INDEX_NAME} IF NOT EXISTS "
            f"FOR (n:{labels_part}) ON EACH [{props_part}]"
        )
        await session.run(fulltext_cypher)
        log.debug("ensure_fulltext_index", index=FULLTEXT_INDEX_NAME)

    log.info("graph_indexes_ensured")
