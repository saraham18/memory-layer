"""Tests for the per-user rate limiter."""

from __future__ import annotations

from memory_layer.llm.rate_limiter import UserRateLimiter


class TestUserRateLimiter:
    def test_allows_within_limit(self):
        rl = UserRateLimiter(requests_per_minute=60, burst_size=5)
        for _ in range(5):
            assert rl.allow("user1")

    def test_denies_over_burst(self):
        rl = UserRateLimiter(requests_per_minute=60, burst_size=3)
        for _ in range(3):
            assert rl.allow("user1")
        assert not rl.allow("user1")

    def test_independent_users(self):
        rl = UserRateLimiter(requests_per_minute=60, burst_size=2)
        assert rl.allow("user1")
        assert rl.allow("user1")
        assert not rl.allow("user1")
        # user2 should still have capacity
        assert rl.allow("user2")

    def test_reset_user(self):
        rl = UserRateLimiter(requests_per_minute=60, burst_size=1)
        assert rl.allow("user1")
        assert not rl.allow("user1")
        rl.reset("user1")
        assert rl.allow("user1")

    def test_wait_time(self):
        rl = UserRateLimiter(requests_per_minute=60, burst_size=1)
        assert rl.wait_time("user1") == 0.0
        rl.allow("user1")
        assert rl.wait_time("user1") > 0
