"""Tests for JWT and password hashing."""

from __future__ import annotations

import pytest
from jose import JWTError

from memory_layer.core.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "my-secure-password"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_different_hashes_same_password(self):
        pw = "test123"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2  # bcrypt uses random salt
        assert verify_password(pw, h1)
        assert verify_password(pw, h2)


class TestJWT:
    SECRET = "test-jwt-secret-key"

    def test_create_and_decode(self):
        token = create_access_token("user-123", self.SECRET)
        payload = decode_access_token(token, self.SECRET)
        assert payload["sub"] == "user-123"
        assert "exp" in payload
        assert "iat" in payload

    def test_extra_claims(self):
        token = create_access_token("u1", self.SECRET, extra_claims={"role": "admin"})
        payload = decode_access_token(token, self.SECRET)
        assert payload["role"] == "admin"

    def test_wrong_secret_fails(self):
        token = create_access_token("user", self.SECRET)
        with pytest.raises(JWTError):
            decode_access_token(token, "wrong-secret")

    def test_expired_token(self):
        token = create_access_token("user", self.SECRET, expires_hours=-1)
        with pytest.raises(JWTError):
            decode_access_token(token, self.SECRET)
