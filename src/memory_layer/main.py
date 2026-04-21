"""FastAPI application factory with lifespan management."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from memory_layer.api.dependencies import set_graph_driver, set_llm_router
from memory_layer.api.middleware import setup_middleware
from memory_layer.api.v1.health import router as health_router
from memory_layer.api.v1.router import v1_router
from memory_layer.config import get_settings
from memory_layer.graph.driver import GraphDriver
from memory_layer.graph.indexes import ensure_indexes
from memory_layer.llm.router import LLMRouter

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info("starting", app=settings.app_name, env=settings.app_env)

    # Initialize Neo4j driver
    driver = GraphDriver(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
    set_graph_driver(driver)

    # Ensure graph indexes/constraints
    try:
        await ensure_indexes(driver)
        log.info("neo4j_indexes_ensured")
    except Exception as e:
        log.warning("neo4j_index_setup_failed", error=str(e))

    # Initialize LLM router
    set_llm_router(LLMRouter())

    # Start sleep scheduler in production
    if settings.is_production:
        try:
            from memory_layer.sleep.scheduler import start_scheduler
            start_scheduler(driver, settings)
            log.info("sleep_scheduler_started")
        except Exception as e:
            log.warning("scheduler_start_failed", error=str(e))

    yield

    # Shutdown
    await driver.close()
    log.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Memory Layer",
        description="BYOAK Universal Memory Platform",
        version="0.1.0",
        lifespan=lifespan,
        debug=settings.debug,
    )

    setup_middleware(app)
    app.include_router(health_router)
    app.include_router(v1_router)

    # Mount MCP server
    try:
        from memory_layer.mcp.server import create_mcp_app
        mcp_app = create_mcp_app()
        app.mount("/mcp", mcp_app)
        log.info("mcp_server_mounted")
    except Exception as e:
        log.warning("mcp_mount_failed", error=str(e))

    return app


app = create_app()
