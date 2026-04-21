"""Token-aware context-window budget manager."""

from __future__ import annotations

import tiktoken

# Lazily initialised encoding — ``cl100k_base`` covers GPT-4, Claude, and
# most modern models closely enough for budget estimation.
_ENCODING_NAME = "cl100k_base"
_encoding: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    """Return the cached tiktoken encoding instance."""
    global _encoding  # noqa: PLW0603
    if _encoding is None:
        _encoding = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoding


def count_tokens(text: str) -> int:
    """Return the number of tokens in *text* using the cl100k_base encoding."""
    return len(_get_encoding().encode(text))


class ContextWindowManager:
    """Manages a token budget for building the master context string.

    Parameters
    ----------
    max_tokens:
        Maximum number of tokens that may be accumulated.
    """

    def __init__(self, max_tokens: int = 4000) -> None:
        self._max_tokens = max_tokens
        self._used_tokens: int = 0
        self._segments: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fits(self, text: str) -> bool:
        """Return ``True`` if *text* fits within the remaining budget."""
        return count_tokens(text) <= self.remaining_tokens()

    def add(self, text: str) -> bool:
        """Add *text* to the context if it fits.

        Returns ``True`` if the text was accepted, ``False`` otherwise.
        """
        token_count = count_tokens(text)
        if token_count > self.remaining_tokens():
            return False
        self._segments.append(text)
        self._used_tokens += token_count
        return True

    def remaining_tokens(self) -> int:
        """Return the number of tokens still available."""
        return max(0, self._max_tokens - self._used_tokens)

    @property
    def used_tokens(self) -> int:
        """Number of tokens consumed so far."""
        return self._used_tokens

    @property
    def text(self) -> str:
        """Return the full accumulated context string."""
        return "\n".join(self._segments)
