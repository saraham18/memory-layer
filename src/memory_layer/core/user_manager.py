"""User registration, authentication, and profile management."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import structlog

from memory_layer.config import Settings
from memory_layer.core.auth import hash_password, verify_password
from memory_layer.graph.repository import GraphRepository
from memory_layer.graph.schemas import NodeLabel
from memory_layer.models.auth import RegisterRequest, RegisterResponse, UserProfile

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class UserManager:
    """Handles user lifecycle operations backed by a Neo4j :label:`User` node."""

    def __init__(self, repository: GraphRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(self, request: RegisterRequest) -> RegisterResponse:
        """Create a new :label:`User` node with a bcrypt-hashed password.

        The caller is responsible for checking email uniqueness *before*
        invoking this method (see :meth:`get_user_by_email`).
        """
        user_id = uuid4()
        now = datetime.now(timezone.utc).isoformat()
        password_hashed = hash_password(request.password)

        cypher = (
            f"CREATE (u:{NodeLabel.USER} {{"
            "  id: $id,"
            "  user_id: $user_id,"
            "  email: $email,"
            "  display_name: $display_name,"
            "  password_hash: $password_hash,"
            "  created_at: $created_at"
            "}) RETURN u"
        )
        params = {
            "id": str(user_id),
            "user_id": str(user_id),
            "email": request.email,
            "display_name": request.display_name,
            "password_hash": password_hashed,
            "created_at": now,
        }

        async with self._repository.driver.session() as session:
            await session.run(cypher, params)

        log.info(
            "user_registered",
            user_id=str(user_id),
            email=request.email,
        )

        return RegisterResponse(
            user_id=user_id,
            email=request.email,
            display_name=request.display_name,
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def authenticate(self, email: str, password: str) -> UserProfile | None:
        """Verify credentials and return a :class:`UserProfile` on success.

        Returns ``None`` when the email is unknown or the password does not
        match.
        """
        user_data = await self.get_user_by_email(email)
        if user_data is None:
            log.debug("auth_failed_no_user", email=email)
            return None

        if not verify_password(password, user_data["password_hash"]):
            log.debug("auth_failed_bad_password", email=email)
            return None

        log.info("user_authenticated", user_id=user_data["id"])

        return UserProfile(
            user_id=UUID(user_data["id"]),
            email=user_data["email"],
            display_name=user_data["display_name"],
        )

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    async def get_user(self, user_id: UUID) -> UserProfile | None:
        """Fetch a user by their unique identifier.

        Returns ``None`` if no matching :label:`User` node exists.
        """
        cypher = (
            f"MATCH (u:{NodeLabel.USER}) "
            "WHERE u.id = $id "
            "RETURN u"
        )

        async with self._repository.driver.session() as session:
            result = await session.run(cypher, {"id": str(user_id)})
            record = await result.single()

        if record is None:
            return None

        node = record["u"]
        return UserProfile(
            user_id=UUID(node["id"]),
            email=node["email"],
            display_name=node["display_name"],
        )

    async def get_user_by_email(self, email: str) -> dict | None:
        """Return the raw user dict (including ``password_hash``) for an email.

        This is intentionally *not* a :class:`UserProfile` because it
        includes the hashed password for credential verification.  Returns
        ``None`` if the email is not registered.
        """
        cypher = (
            f"MATCH (u:{NodeLabel.USER}) "
            "WHERE u.email = $email "
            "RETURN u"
        )

        async with self._repository.driver.session() as session:
            result = await session.run(cypher, {"email": email})
            record = await result.single()

        if record is None:
            return None

        node = record["u"]
        return dict(node)
