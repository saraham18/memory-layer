"""State definitions for the LangGraph extraction workflow."""

from __future__ import annotations

from typing import TypedDict


class ExtractionState(TypedDict, total=False):
    """Typed state dictionary passed through the LangGraph extraction graph.

    Fields:
        text:       The original input text to process.
        chunks:     Text split into processable chunks.
        nodes:      Extracted node dicts (entities, goals, assertions).
        edges:      Extracted relationship dicts.
        validated:  Whether the extraction has been validated.
        committed:  Whether the nodes/edges have been committed to the graph.
        errors:     A list of error messages accumulated during processing.
        retries:    Number of retry attempts so far.
        user_id:    The tenant user id (as a string).
        content_type: The content type of the ingested text.
        metadata:   Additional metadata for the ingest.
        ingest_id:  The UUID (as a string) for this ingest run.
    """

    text: str
    chunks: list[str]
    nodes: list[dict]
    edges: list[dict]
    validated: bool
    committed: bool
    errors: list[str]
    retries: int
    user_id: str
    content_type: str
    metadata: dict
    ingest_id: str
