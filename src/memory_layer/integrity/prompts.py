"""LLM prompts for the integrity system (contradiction checking & resolution)."""

from __future__ import annotations

CONTRADICTION_CHECK_SYSTEM = (
    "You are a knowledge-graph integrity analyst.  You compare two factual "
    "assertions and classify their relationship.  Respond ONLY with valid JSON."
)

CONTRADICTION_CHECK_PROMPT = """\
Compare the following two factual assertions and classify their relationship.

Existing assertion (already committed to the knowledge graph):
\"\"\"{existing_assertion}\"\"\"

New assertion (pending commit):
\"\"\"{new_assertion}\"\"\"

Classify the relationship as exactly ONE of:
- "contradiction" — the two assertions cannot both be true at the same time.
- "update" — the new assertion refines, corrects, or supersedes the existing \
one (e.g. a more recent value for the same fact).
- "compatible" — the two assertions are consistent and can coexist.

Respond with a JSON object:
{{
    "classification": "<contradiction | update | compatible>",
    "reasoning": "<one-sentence explanation>"
}}
"""

RESOLUTION_SYSTEM = (
    "You are a knowledge-graph conflict resolver.  Given two contradicting "
    "assertions you suggest a resolution strategy.  Respond ONLY with valid JSON."
)

RESOLUTION_PROMPT = """\
Two assertions in the knowledge graph contradict each other.

Assertion A:
\"\"\"{assertion_a}\"\"\"

Assertion B:
\"\"\"{assertion_b}\"\"\"

Suggest a resolution.  Pick exactly ONE strategy:
- "keep_a" — Assertion A is more likely correct; deprecate B.
- "keep_b" — Assertion B is more likely correct; deprecate A.
- "merge" — Both contain partial truth; propose a merged assertion.
- "flag" — Cannot determine automatically; flag for human review.

Respond with a JSON object:
{{
    "strategy": "<keep_a | keep_b | merge | flag>",
    "merged_content": "<merged assertion text if strategy is 'merge', else null>",
    "reasoning": "<one-sentence explanation>"
}}
"""
