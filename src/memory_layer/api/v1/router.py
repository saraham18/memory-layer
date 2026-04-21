"""Aggregated v1 API router."""

from __future__ import annotations

from fastapi import APIRouter

from memory_layer.api.v1 import admin, auth, graph, ingest, keys, query

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth.router)
v1_router.include_router(keys.router)
v1_router.include_router(ingest.router)
v1_router.include_router(query.router)
v1_router.include_router(graph.router)
v1_router.include_router(admin.router)
