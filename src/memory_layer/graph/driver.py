"""AsyncDriver lifecycle and connection-pool management for Neo4j."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession

from memory_layer.config import get_settings

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class GraphDriver:
    """Thin wrapper around :class:`neo4j.AsyncDriver`.

    Manages a single driver instance (with its built-in connection pool)
    and exposes a convenience ``session()`` async context manager that
    returns an :class:`neo4j.AsyncSession` bound to the configured
    database.
    """

    def __init__(
        self,
        uri: str | None = None,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        settings = get_settings()
        self._uri = uri or settings.neo4j_uri
        self._username = username or settings.neo4j_username
        self._password = password or settings.neo4j_password
        self._database = database or settings.neo4j_database
        self._driver: AsyncDriver | None = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._username, self._password),
        )
        log.info("neo4j_driver_created", uri=self._uri, database=self._database)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def verify_connectivity(self) -> None:
        """Verify the driver can connect to Neo4j."""
        await self.driver.verify_connectivity()

    async def close(self) -> None:
        """Gracefully close the driver and release pooled connections."""
        if self._driver is not None:
            await self._driver.close()
            log.info("neo4j_driver_closed")
            self._driver = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def driver(self) -> AsyncDriver:
        """Return the underlying :class:`neo4j.AsyncDriver`.

        Raises :class:`RuntimeError` when accessed before ``init()``.
        """
        if self._driver is None:
            raise RuntimeError(
                "GraphDriver has not been initialised.  Call `await graph_driver.init()` first."
            )
        return self._driver

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield an :class:`neo4j.AsyncSession` scoped to the configured database."""
        session = self.driver.session(database=self._database)
        try:
            yield session
        finally:
            await session.close()
