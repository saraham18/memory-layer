"""Lightweight spaCy pipeline builder for text chunking and sentence splitting."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import spacy

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_DEFAULT_MAX_CHUNK_SIZE: int = 2000


def build_spacy_pipeline() -> spacy.Language:
    """Build a minimal spaCy pipeline with a sentenciser.

    Uses the rule-based ``sentencizer`` component so that no statistical
    model download is required.
    """
    import spacy  # noqa: WPS433 — deferred import to keep startup fast

    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


def chunk_text(
    text: str,
    max_chunk_size: int = _DEFAULT_MAX_CHUNK_SIZE,
) -> list[str]:
    """Split *text* into chunks of at most *max_chunk_size* characters.

    Sentence boundaries (detected via spaCy) are respected so that a chunk
    never starts or ends in the middle of a sentence unless a single sentence
    exceeds *max_chunk_size*.
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # Short-circuit: entire text fits in one chunk.
    if len(text) <= max_chunk_size:
        return [text]

    nlp = build_spacy_pipeline()
    doc = nlp(text)
    sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for sentence in sentences:
        sent_len = len(sentence)

        # If a single sentence exceeds the limit, hard-split it.
        if sent_len > max_chunk_size:
            # Flush what we have first.
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0
            # Hard-split the oversized sentence.
            for start in range(0, sent_len, max_chunk_size):
                chunks.append(sentence[start : start + max_chunk_size])
            continue

        # Adding this sentence would exceed the budget — flush.
        separator_len = 1 if current_chunk else 0
        if current_length + separator_len + sent_len > max_chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_length = 0

        current_chunk.append(sentence)
        current_length += (1 if current_length else 0) + sent_len

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    log.debug("text_chunked", num_chunks=len(chunks), total_length=len(text))
    return chunks
