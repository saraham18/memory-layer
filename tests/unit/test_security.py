"""Tests for Fernet encryption."""

from __future__ import annotations

import pytest

from memory_layer.core.security import KeyEncryptor


class TestKeyEncryptor:
    def test_encrypt_decrypt_roundtrip(self):
        key = KeyEncryptor.generate_key()
        enc = KeyEncryptor([key])
        plaintext = "sk-test-api-key-12345"
        ciphertext = enc.encrypt(plaintext)
        assert ciphertext != plaintext
        assert enc.decrypt(ciphertext) == plaintext

    def test_different_ciphertexts_same_plaintext(self):
        key = KeyEncryptor.generate_key()
        enc = KeyEncryptor([key])
        pt = "my-secret-key"
        c1 = enc.encrypt(pt)
        c2 = enc.encrypt(pt)
        # Fernet uses random IV, so ciphertexts differ
        assert c1 != c2
        assert enc.decrypt(c1) == pt
        assert enc.decrypt(c2) == pt

    def test_key_rotation(self):
        old_key = KeyEncryptor.generate_key()
        new_key = KeyEncryptor.generate_key()

        # Encrypt with old key
        old_enc = KeyEncryptor([old_key])
        ciphertext = old_enc.encrypt("secret")

        # Create encryptor with new key primary, old key secondary
        rotated_enc = KeyEncryptor([new_key, old_key])
        assert rotated_enc.decrypt(ciphertext) == "secret"

        # Rotate to new key
        new_ciphertext = rotated_enc.rotate(ciphertext)
        assert new_ciphertext != ciphertext

        # Can decrypt with new key only
        new_only = KeyEncryptor([new_key])
        assert new_only.decrypt(new_ciphertext) == "secret"

    def test_no_keys_raises(self):
        with pytest.raises(ValueError, match="At least one Fernet key"):
            KeyEncryptor([])

    def test_generate_key_is_valid(self):
        key = KeyEncryptor.generate_key()
        enc = KeyEncryptor([key])
        assert enc.decrypt(enc.encrypt("test")) == "test"
