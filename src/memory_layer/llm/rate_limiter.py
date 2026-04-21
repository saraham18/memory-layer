"""Per-user LLM rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)

    def consume(self, amount: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

    @property
    def wait_time(self) -> float:
        if self.tokens >= 1.0:
            return 0.0
        return (1.0 - self.tokens) / self.refill_rate


class UserRateLimiter:
    """Per-user token bucket rate limiter for LLM calls."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int | None = None,
    ) -> None:
        self._rpm = requests_per_minute
        self._burst = burst_size or requests_per_minute
        self._buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(
                capacity=float(self._burst),
                refill_rate=self._rpm / 60.0,
                tokens=float(self._burst),
            )
        )

    def allow(self, user_id: str) -> bool:
        return self._buckets[user_id].consume()

    def wait_time(self, user_id: str) -> float:
        return self._buckets[user_id].wait_time

    def reset(self, user_id: str) -> None:
        self._buckets.pop(user_id, None)
