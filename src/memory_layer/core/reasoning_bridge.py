"""Bridge between natural language queries and the knowledge graph.

The :class:`ReasoningBridge` translates free-form user queries into
graph-friendly search terms and, conversely, formats raw subgraph data
back into a coherent natural language context block that can be injected
into an LLM prompt as "Master Context".
"""

from __future__ import annotations

import json

import structlog

from memory_layer.llm.base import BaseLLMClient

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ------------------------------------------------------------------
# Prompt templates
# ------------------------------------------------------------------

_SEED_EXTRACTION_SYSTEM = (
    "You are a query analysis assistant for a personal knowledge graph. "
    "Given a user's natural language question, extract a JSON array of short, "
    "specific search terms (strings) that would be useful for querying a "
    "knowledge graph. Return ONLY a JSON array of strings, nothing else.\n\n"
    "Guidelines:\n"
    "- Extract key entities, concepts, and topics from the query.\n"
    "- Include synonyms or alternative phrasings where appropriate.\n"
    "- Keep each term concise (1-4 words).\n"
    "- Return between 2 and 8 terms.\n"
    "- Do NOT include generic stop-words or filler."
)

_SEED_EXTRACTION_PROMPT = "Extract search terms from this query:\n\n{query}"

_CONTEXT_FORMAT_SYSTEM = (
    "You are a context synthesis assistant. Given raw knowledge graph data "
    "(nodes and relationships) and the user's original query, produce a "
    "concise natural language summary that captures all relevant facts, "
    "relationships, and context. This summary will be injected into a "
    "subsequent LLM prompt as background knowledge.\n\n"
    "Guidelines:\n"
    "- Write in clear, factual prose.\n"
    "- Preserve important details, dates, and confidence scores.\n"
    "- Organise information logically (group related facts).\n"
    "- Note any contradictions or low-confidence assertions.\n"
    "- Keep the summary focused on what is relevant to the query.\n"
    "- If the data is empty, say so explicitly."
)

_CONTEXT_FORMAT_PROMPT = (
    "Original query: {query}\n\n"
    "Knowledge graph data:\n{data}\n\n"
    "Produce a Master Context summary."
)


class ReasoningBridge:
    """Translates between natural language and knowledge-graph representations.

    This class acts as the semantic glue between the user-facing LLM
    conversation and the structured graph retrieval layer.
    """

    # ------------------------------------------------------------------
    # Query -> search terms
    # ------------------------------------------------------------------

    async def translate_query(
        self, query: str, llm_client: BaseLLMClient
    ) -> list[str]:
        """Use an LLM to decompose a natural language query into seed search terms.

        Parameters
        ----------
        query:
            The user's free-form question.
        llm_client:
            An initialised LLM client that implements :meth:`complete`.

        Returns
        -------
        list[str]
            A list of 2-8 concise search terms suitable for fulltext
            graph queries.
        """
        prompt = _SEED_EXTRACTION_PROMPT.format(query=query)

        log.debug("translate_query_start", query=query)

        try:
            response = await llm_client.complete_json(
                prompt=prompt,
                system=_SEED_EXTRACTION_SYSTEM,
                temperature=0.0,
                max_tokens=512,
            )
            # complete_json returns a parsed dict; we expect a list at the top level
            if isinstance(response, list):
                terms = [str(t) for t in response]
            elif isinstance(response, dict) and "terms" in response:
                terms = [str(t) for t in response["terms"]]
            else:
                # Fallback: try to extract any list value from the dict
                for value in response.values():
                    if isinstance(value, list):
                        terms = [str(t) for t in value]
                        break
                else:
                    log.warning("translate_query_unexpected_format", response=response)
                    terms = [query]
        except Exception:
            log.exception("translate_query_llm_error", query=query)
            # Graceful degradation: use the raw query as a single search term
            terms = [query]

        log.info("translate_query_done", query=query, terms=terms)
        return terms

    # ------------------------------------------------------------------
    # Subgraph -> natural language context
    # ------------------------------------------------------------------

    async def format_context(
        self,
        subgraph_data: dict,
        query: str,
        llm_client: BaseLLMClient | None = None,
    ) -> str:
        """Format retrieved subgraph data into a natural language context block.

        When an ``llm_client`` is provided, the LLM is used to produce a
        polished prose summary.  Without one, a deterministic template-based
        rendering is returned (useful in tests or when no LLM budget is
        available).

        Parameters
        ----------
        subgraph_data:
            A dict with ``"nodes"`` and ``"edges"`` lists as returned by
            the retrieval layer.
        query:
            The original user query (used to focus the summary).
        llm_client:
            Optional LLM client for AI-powered summarisation.

        Returns
        -------
        str
            A "Master Context" block ready for injection into an LLM prompt.
        """
        nodes = subgraph_data.get("nodes", [])
        edges = subgraph_data.get("edges", [])

        if not nodes and not edges:
            return "No relevant information was found in the knowledge graph."

        # Build a serialisable representation for the LLM
        data_text = json.dumps(subgraph_data, indent=2, default=str)

        if llm_client is not None:
            return await self._format_with_llm(data_text, query, llm_client)

        # Deterministic fallback
        return self._format_deterministic(nodes, edges)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _format_with_llm(
        self, data_text: str, query: str, llm_client: BaseLLMClient
    ) -> str:
        """Use the LLM to produce a polished Master Context summary."""
        prompt = _CONTEXT_FORMAT_PROMPT.format(query=query, data=data_text)

        try:
            response = await llm_client.complete(
                prompt=prompt,
                system=_CONTEXT_FORMAT_SYSTEM,
                temperature=0.0,
                max_tokens=2048,
            )
            log.info("format_context_llm_done", query=query, length=len(response.content))
            return response.content
        except Exception:
            log.exception("format_context_llm_error", query=query)
            # Fall back to deterministic rendering on LLM failure
            return self._format_deterministic(
                json.loads(data_text).get("nodes", []),
                json.loads(data_text).get("edges", []),
            )

    @staticmethod
    def _format_deterministic(nodes: list[dict], edges: list[dict]) -> str:
        """Produce a simple template-based context from raw graph data."""
        lines: list[str] = ["## Master Context", ""]

        if nodes:
            lines.append(f"### Retrieved Nodes ({len(nodes)})")
            for node in nodes:
                name = node.get("name", node.get("content", node.get("id", "unknown")))
                label = node.get("label", node.get("entity_type", "Node"))
                confidence = node.get("confidence", "n/a")
                lines.append(f"- **{name}** ({label}, confidence: {confidence})")
            lines.append("")

        if edges:
            lines.append(f"### Relationships ({len(edges)})")
            for edge in edges:
                src = edge.get("source_id", "?")
                tgt = edge.get("target_id", "?")
                rel = edge.get("relationship", edge.get("rel_type", "RELATED_TO"))
                lines.append(f"- {src} --[{rel}]--> {tgt}")
            lines.append("")

        return "\n".join(lines)
