"""Consolidation and pruning prompts for the Digital Sleep Cycle."""

from __future__ import annotations

CONSOLIDATION_PROMPT = """\
You are a knowledge consolidation engine. Given a list of raw factual assertions \
extracted from recent conversations, distill them into a minimal set of Atomic Facts.

Rules:
- Merge redundant or overlapping assertions into single, precise statements
- Preserve all unique information — do not discard novel facts
- Each Atomic Fact should be self-contained and unambiguous
- Remove purely ephemeral or conversational content (greetings, filler)
- Assign a confidence score (0.0-1.0) to each Atomic Fact

Input assertions (JSON array):
{assertions}

Respond with a JSON object:
{{
  "atomic_facts": [
    {{"content": "...", "confidence": 0.95, "source_ids": ["id1", "id2"]}},
    ...
  ],
  "pruned_ids": ["id_of_ephemeral_assertion", ...]
}}
"""

EPHEMERAL_CHECK_PROMPT = """\
Classify each of the following graph nodes as either "persistent" (worth keeping long-term) \
or "ephemeral" (temporary, conversational, no lasting value).

Nodes:
{nodes}

Respond with a JSON object:
{{
  "classifications": [
    {{"id": "node_id", "classification": "persistent|ephemeral", "reason": "..."}},
    ...
  ]
}}
"""
