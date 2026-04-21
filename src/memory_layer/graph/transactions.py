"""Atomic transaction wrappers for executing Cypher against Neo4j."""

from __future__ import annotations

from typing import Any

import structlog
from neo4j import AsyncManagedTransaction, Record

from memory_layer.graph.driver import GraphDriver

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def execute_read(
    driver: GraphDriver,
    query: str,
    params: dict[str, Any] | None = None,
) -> list[Record]:
    """Run a **read** transaction and return all result records.

    The transaction is automatically committed on success or rolled back on
    failure by the Neo4j driver.
    """
    params = params or {}

    async def _work(tx: AsyncManagedTransaction) -> list[Record]:
        result = await tx.run(query, params)
        return [record async for record in result]

    async with driver.session() as session:
        records = await session.execute_read(_work)

    log.debug("execute_read", query=query[:120], param_keys=list(params.keys()))
    return records


async def execute_write(
    driver: GraphDriver,
    query: str,
    params: dict[str, Any] | None = None,
) -> list[Record]:
    """Run a **write** transaction and return all result records."""
    params = params or {}

    async def _work(tx: AsyncManagedTransaction) -> list[Record]:
        result = await tx.run(query, params)
        return [record async for record in result]

    async with driver.session() as session:
        records = await session.execute_write(_work)

    log.debug("execute_write", query=query[:120], param_keys=list(params.keys()))
    return records


async def execute_write_batch(
    driver: GraphDriver,
    queries_and_params: list[tuple[str, dict[str, Any]]],
) -> list[list[Record]]:
    """Execute multiple write statements inside a **single** transaction.

    All statements succeed or fail atomically.  Returns one list of records
    per statement, in order.
    """

    async def _work(tx: AsyncManagedTransaction) -> list[list[Record]]:
        all_records: list[list[Record]] = []
        for query, params in queries_and_params:
            result = await tx.run(query, params)
            records = [record async for record in result]
            all_records.append(records)
        return all_records

    async with driver.session() as session:
        all_records = await session.execute_write(_work)

    log.debug(
        "execute_write_batch",
        statement_count=len(queries_and_params),
    )
    return all_records
