"""Fernet AES encryption for API key storage with MultiFernet rotation support."""

from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet


class KeyEncryptor:
    """Encrypts/decrypts user API keys using MultiFernet for key rotation."""

    def __init__(self, fernet_keys: list[str]) -> None:
        if not fernet_keys:
            raise ValueError("At least one Fernet key is required")
        fernets = [Fernet(k.encode() if isinstance(k, str) else k) for k in fernet_keys]
        self._multi = MultiFernet(fernets)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext API key, return base64 ciphertext."""
        return self._multi.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext back to the original API key."""
        return self._multi.decrypt(ciphertext.encode()).decode()

    def rotate(self, ciphertext: str) -> str:
        """Re-encrypt with the current primary key (for key rotation)."""
        return self._multi.rotate(ciphertext.encode()).decode()

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key."""
        return Fernet.generate_key().decode()
