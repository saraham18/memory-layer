"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from memory_layer.api.dependencies import get_graph_driver
from memory_layer.graph.driver import GraphDriver

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready(driver: GraphDriver = Depends(get_graph_driver)) -> dict:
    try:
        await driver.verify_connectivity()
        return {"status": "ready", "neo4j": "connected"}
    except Exception as e:
        return {"status": "degraded", "neo4j": str(e)}
