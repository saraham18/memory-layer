"""LLM prompt templates for knowledge extraction."""

from __future__ import annotations

ENTITY_EXTRACTION_PROMPT: str = """\
You are an expert information extraction system.  Analyze the following text
and extract all notable **entities** (people, organisations, places, products,
technologies, events, etc.).

For each entity return a JSON object with these fields:
  - "name"        : the canonical name of the entity (string)
  - "entity_type" : the category (e.g. "Person", "Organisation", "Place",
                    "Technology", "Product", "Event", "Other") (string)
  - "description" : a one-sentence description based only on what the text
                    states about this entity (string)

Return a JSON object with a single key "entities" whose value is a list of
the extracted entity objects.  If no entities are found, return:
  {{"entities": []}}

TEXT:
---
{text}
---
"""

GOAL_EXTRACTION_PROMPT: str = """\
You are an expert at understanding user intent.  Analyze the following text
and extract any **goals**, **intentions**, or **desired outcomes** expressed
by the user or implied by the context.

For each goal return a JSON object with these fields:
  - "description" : a concise description of the goal (string)
  - "priority"    : one of "high", "medium", or "low" (string)
  - "status"      : one of "active", "completed", or "uncertain" (string)

Return a JSON object with a single key "goals" whose value is a list of
the extracted goal objects.  If no goals are found, return:
  {{"goals": []}}

TEXT:
---
{text}
---
"""

ASSERTION_EXTRACTION_PROMPT: str = """\
You are an expert at identifying factual claims.  Analyze the following text
and extract all **factual assertions** or **claims** made.

For each assertion return a JSON object with these fields:
  - "content"    : the assertion expressed as a declarative statement (string)
  - "confidence" : your confidence that this is indeed stated in the text,
                   on a scale from 0.0 to 1.0 (float)
  - "source_hint": a short phrase indicating where in the text this was
                   found, e.g. a quote fragment (string)

Return a JSON object with a single key "assertions" whose value is a list
of the extracted assertion objects.  If none are found, return:
  {{"assertions": []}}

TEXT:
---
{text}
---
"""

RELATIONSHIP_EXTRACTION_PROMPT: str = """\
You are an expert at identifying relationships between concepts.  You are
given a piece of text **and** a list of already-extracted nodes.  Identify
directed relationships between those nodes.

Each node has a temporary "temp_id" you must reference.

Available relationship types:
  DEPENDS_ON, CONTRADICTS, SUPPORTS, RELATED_TO, HAS_GOAL, ASSERTS,
  DERIVED_FROM, PART_OF, SUPERSEDES, INVOLVES, REQUIRES

For each relationship return a JSON object with these fields:
  - "source_id" : temp_id of the source node (string)
  - "target_id" : temp_id of the target node (string)
  - "rel_type"  : one of the relationship types listed above (string)
  - "description": brief justification for this edge (string)

Return a JSON object with a single key "relationships" whose value is a list
of the extracted relationship objects.  If none are found, return:
  {{"relationships": []}}

NODES:
{nodes_json}

TEXT:
---
{text}
---
"""
