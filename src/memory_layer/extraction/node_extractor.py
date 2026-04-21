"""Entity, goal, and assertion extraction via LLM."""

from __future__ import annotations

import asyncio
import uuid

import structlog

from memory_layer.extraction.prompts import (
    ASSERTION_EXTRACTION_PROMPT,
    ENTITY_EXTRACTION_PROMPT,
    GOAL_EXTRACTION_PROMPT,
)
from memory_layer.extraction.validators import validate_entities
from memory_layer.llm.base import BaseLLMClient

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class NodeExtractor:
    """Extracts entities, goals, and assertions from text using an LLM."""

    def __init__(self, llm_client: BaseLLMClient) -> None:
        self._llm = llm_client

    # ------------------------------------------------------------------
    # Individual extractors
    # ------------------------------------------------------------------

    async def extract_entities(self, text: str) -> list[dict]:
        """Extract entities from *text* using the entity prompt."""
        prompt = ENTITY_EXTRACTION_PROMPT.format(text=text)
        result = await self._llm.complete_json(
            prompt=prompt,
            system="You are a precise information extraction engine. Return valid JSON only.",
            temperature=0.0,
        )
        raw_entities = result.get("entities", [])
        entities = validate_entities(raw_entities)
        for entity in entities:
            entity["temp_id"] = str(uuid.uuid4())
            entity["label"] = "Entity"
        log.debug("entities_extracted", count=len(entities))
        return entities

    async def extract_goals(self, text: str) -> list[dict]:
        """Extract user goals/intentions from *text*."""
        prompt = GOAL_EXTRACTION_PROMPT.format(text=text)
        result = await self._llm.complete_json(
            prompt=prompt,
            system="You are a precise information extraction engine. Return valid JSON only.",
            temperature=0.0,
        )
        raw_goals = result.get("goals", [])
        goals: list[dict] = []
        for item in raw_goals:
            if not isinstance(item, dict):
                continue
            description = item.get("description", "")
            if not description or not isinstance(description, str):
                continue
            item["temp_id"] = str(uuid.uuid4())
            item["label"] = "UserGoal"
            item.setdefault("priority", "medium")
            item.setdefault("status", "active")
            goals.append(item)
        log.debug("goals_extracted", count=len(goals))
        return goals

    async def extract_assertions(self, text: str) -> list[dict]:
        """Extract factual assertions from *text*."""
        prompt = ASSERTION_EXTRACTION_PROMPT.format(text=text)
        result = await self._llm.complete_json(
            prompt=prompt,
            system="You are a precise information extraction engine. Return valid JSON only.",
            temperature=0.0,
        )
        raw_assertions = result.get("assertions", [])
        assertions: list[dict] = []
        for item in raw_assertions:
            if not isinstance(item, dict):
                continue
            content = item.get("content", "")
            if not content or not isinstance(content, str):
                continue
            item["temp_id"] = str(uuid.uuid4())
            item["label"] = "FactualAssertion"
            item.setdefault("confidence", 0.5)
            # Clamp confidence to [0.0, 1.0].
            try:
                item["confidence"] = max(0.0, min(1.0, float(item["confidence"])))
            except (TypeError, ValueError):
                item["confidence"] = 0.5
            assertions.append(item)
        log.debug("assertions_extracted", count=len(assertions))
        return assertions

    # ------------------------------------------------------------------
    # Combined extraction
    # ------------------------------------------------------------------

    async def extract_all(self, text: str) -> list[dict]:
        """Run all three extraction passes concurrently and combine results."""
        entities, goals, assertions = await asyncio.gather(
            self.extract_entities(text),
            self.extract_goals(text),
            self.extract_assertions(text),
        )
        combined = entities + goals + assertions
        log.info(
            "all_nodes_extracted",
            entities=len(entities),
            goals=len(goals),
            assertions=len(assertions),
            total=len(combined),
        )
        return combined
