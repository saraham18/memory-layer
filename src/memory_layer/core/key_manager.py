"""API key storage, retrieval, and lifecycle management."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import structlog

from memory_layer.core.security import KeyEncryptor
from memory_layer.graph.repository import GraphRepository
from memory_layer.graph.schemas import NodeLabel, RelationType
from memory_layer.models.keys import (
    KeyCreateRequest,
    KeyListResponse,
    KeyResponse,
    KeyUpdateRequest,
    KeyValidateResponse,
    LLMProvider,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class KeyManager:
    """Manages encrypted LLM API keys stored as :label:`APIKey` nodes in Neo4j.

    Each key is AES-encrypted at rest via :class:`KeyEncryptor` and linked
    to its owning :label:`User` node through an :rel:`OWNS_KEY` relationship.
    """

    def __init__(self, repository: GraphRepository, encryptor: KeyEncryptor) -> None:
        self._repository = repository
        self._encryptor = encryptor

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def store_key(self, user_id: UUID, request: KeyCreateRequest) -> KeyResponse:
        """Encrypt and persist a new API key, linking it to the user."""
        key_id = uuid4()
        now = datetime.now(timezone.utc)
        encrypted = self._encryptor.encrypt(request.api_key)

        cypher = (
            f"MATCH (u:{NodeLabel.USER}) WHERE u.id = $user_id "
            f"CREATE (k:{NodeLabel.API_KEY} {{"
            "  id: $key_id,"
            "  user_id: $user_id,"
            "  provider: $provider,"
            "  label: $label,"
            "  key_hash: $key_hash,"
            "  created_at: $created_at"
            "}) "
            f"CREATE (u)-[:{RelationType.OWNS_KEY}]->(k) "
            "RETURN k"
        )
        params = {
            "user_id": str(user_id),
            "key_id": str(key_id),
            "provider": request.provider.value,
            "label": request.label,
            "key_hash": encrypted,
            "created_at": now.isoformat(),
        }

        async with self._repository.driver.session() as session:
            await session.run(cypher, params)

        log.info(
            "key_stored",
            user_id=str(user_id),
            key_id=str(key_id),
            provider=request.provider.value,
        )

        return KeyResponse(
            key_id=key_id,
            provider=request.provider,
            label=request.label,
            created_at=now,
            masked_key=self._mask_key(request.api_key),
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_keys(self, user_id: UUID) -> KeyListResponse:
        """List all API keys for a user (masked, never plaintext)."""
        cypher = (
            f"MATCH (u:{NodeLabel.USER})-[:{RelationType.OWNS_KEY}]->(k:{NodeLabel.API_KEY}) "
            "WHERE u.id = $user_id "
            "RETURN k ORDER BY k.created_at DESC"
        )

        keys: list[KeyResponse] = []
        async with self._repository.driver.session() as session:
            result = await session.run(cypher, {"user_id": str(user_id)})
            records = [record async for record in result]

        for record in records:
            node = record["k"]
            decrypted = self._encryptor.decrypt(node["key_hash"])
            keys.append(
                KeyResponse(
                    key_id=UUID(node["id"]),
                    provider=LLMProvider(node["provider"]),
                    label=node["label"],
                    created_at=datetime.fromisoformat(node["created_at"]),
                    last_used=datetime.fromisoformat(node["last_used"]) if node.get("last_used") else None,
                    is_valid=node.get("is_valid"),
                    masked_key=self._mask_key(decrypted),
                )
            )

        return KeyListResponse(keys=keys)

    async def get_key(self, user_id: UUID, key_id: UUID) -> KeyResponse | None:
        """Retrieve a single key's metadata (masked) by its identifier."""
        node = await self._fetch_key_node(user_id, key_id)
        if node is None:
            return None

        decrypted = self._encryptor.decrypt(node["key_hash"])
        return KeyResponse(
            key_id=UUID(node["id"]),
            provider=LLMProvider(node["provider"]),
            label=node["label"],
            created_at=datetime.fromisoformat(node["created_at"]),
            last_used=datetime.fromisoformat(node["last_used"]) if node.get("last_used") else None,
            is_valid=node.get("is_valid"),
            masked_key=self._mask_key(decrypted),
        )

    async def get_decrypted_key(self, user_id: UUID, key_id: UUID) -> str:
        """Return the plaintext API key (for making LLM calls).

        Raises :class:`ValueError` if the key does not exist.
        """
        node = await self._fetch_key_node(user_id, key_id)
        if node is None:
            raise ValueError(f"Key {key_id} not found for user {user_id}")
        return self._encryptor.decrypt(node["key_hash"])

    async def get_key_for_provider(self, user_id: UUID, provider: LLMProvider) -> str:
        """Convenience method: return the first decrypted key for a provider.

        Raises :class:`ValueError` if no key is stored for the provider.
        """
        cypher = (
            f"MATCH (u:{NodeLabel.USER})-[:{RelationType.OWNS_KEY}]->(k:{NodeLabel.API_KEY}) "
            "WHERE u.id = $user_id AND k.provider = $provider "
            "RETURN k LIMIT 1"
        )

        async with self._repository.driver.session() as session:
            result = await session.run(
                cypher,
                {"user_id": str(user_id), "provider": provider.value if hasattr(provider, "value") else str(provider)},
            )
            record = await result.single()

        if record is None:
            provider_name = provider.value if hasattr(provider, "value") else str(provider)
            raise ValueError(
                f"No {provider_name} key found for user {user_id}"
            )

        return self._encryptor.decrypt(record["k"]["key_hash"])

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_key(
        self, user_id: UUID, key_id: UUID, request: KeyUpdateRequest
    ) -> KeyResponse | None:
        """Update an existing key's encrypted value and/or label."""
        node = await self._fetch_key_node(user_id, key_id)
        if node is None:
            return None

        encrypted = self._encryptor.encrypt(request.api_key)
        now = datetime.now(timezone.utc).isoformat()

        set_clauses = ["k.key_hash = $key_hash", "k.updated_at = $updated_at"]
        params: dict = {
            "user_id": str(user_id),
            "key_id": str(key_id),
            "key_hash": encrypted,
            "updated_at": now,
        }

        if request.label is not None:
            set_clauses.append("k.label = $label")
            params["label"] = request.label

        set_expr = ", ".join(set_clauses)
        cypher = (
            f"MATCH (u:{NodeLabel.USER})-[:{RelationType.OWNS_KEY}]->(k:{NodeLabel.API_KEY}) "
            "WHERE u.id = $user_id AND k.id = $key_id "
            f"SET {set_expr} "
            "RETURN k"
        )

        async with self._repository.driver.session() as session:
            result = await session.run(cypher, params)
            record = await result.single()

        if record is None:
            return None

        updated_node = record["k"]
        decrypted = self._encryptor.decrypt(updated_node["key_hash"])

        log.info("key_updated", user_id=str(user_id), key_id=str(key_id))

        return KeyResponse(
            key_id=UUID(updated_node["id"]),
            provider=LLMProvider(updated_node["provider"]),
            label=updated_node["label"],
            created_at=datetime.fromisoformat(updated_node["created_at"]),
            last_used=(
                datetime.fromisoformat(updated_node["last_used"])
                if updated_node.get("last_used")
                else None
            ),
            is_valid=updated_node.get("is_valid"),
            masked_key=self._mask_key(decrypted),
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_key(self, user_id: UUID, key_id: UUID) -> bool:
        """Remove an :label:`APIKey` node and its :rel:`OWNS_KEY` edge.

        Returns ``True`` if a key was deleted, ``False`` otherwise.
        """
        cypher = (
            f"MATCH (u:{NodeLabel.USER})-[r:{RelationType.OWNS_KEY}]->(k:{NodeLabel.API_KEY}) "
            "WHERE u.id = $user_id AND k.id = $key_id "
            "DETACH DELETE k "
            "RETURN count(k) AS deleted"
        )

        async with self._repository.driver.session() as session:
            result = await session.run(
                cypher,
                {"user_id": str(user_id), "key_id": str(key_id)},
            )
            record = await result.single()

        deleted = record is not None and record["deleted"] > 0
        if deleted:
            log.info("key_deleted", user_id=str(user_id), key_id=str(key_id))
        return deleted

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_key(self, user_id: UUID, key_id: UUID) -> KeyValidateResponse | None:
        """Validate that a stored key exists and can be decrypted.

        This is a *placeholder* implementation that confirms the key is
        readable.  A production version would make a lightweight provider
        API call (e.g. ``GET /models``) to verify the key is still active.
        """
        node = await self._fetch_key_node(user_id, key_id)
        if node is None:
            return None

        try:
            self._encryptor.decrypt(node["key_hash"])
            is_valid = True
            message = "Key is stored and decryptable"
        except Exception:
            is_valid = False
            message = "Key could not be decrypted — consider re-storing it"

        return KeyValidateResponse(
            key_id=UUID(node["id"]),
            provider=LLMProvider(node["provider"]),
            is_valid=is_valid,
            message=message,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_key_node(self, user_id: UUID, key_id: UUID) -> dict | None:
        """Fetch the raw Neo4j node dict for an :label:`APIKey`."""
        cypher = (
            f"MATCH (u:{NodeLabel.USER})-[:{RelationType.OWNS_KEY}]->(k:{NodeLabel.API_KEY}) "
            "WHERE u.id = $user_id AND k.id = $key_id "
            "RETURN k"
        )

        async with self._repository.driver.session() as session:
            result = await session.run(
                cypher,
                {"user_id": str(user_id), "key_id": str(key_id)},
            )
            record = await result.single()

        if record is None:
            return None
        return dict(record["k"])

    @staticmethod
    def _mask_key(key: str) -> str:
        """Mask an API key, showing only the first 4 and last 4 characters.

        Example::

            >>> KeyManager._mask_key("sk-abcdefghijklmnop-wxyz")
            'sk-a...wxyz'
        """
        if len(key) <= 8:
            return "****"
        return f"{key[:4]}...{key[-4:]}"
