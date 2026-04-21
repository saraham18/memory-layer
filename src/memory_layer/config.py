"""Application configuration via Pydantic Settings."""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "memory-layer"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me"

    # JWT
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # Fernet — list of base64-encoded keys for MultiFernet rotation
    fernet_keys: list[str] = []

    @field_validator("fernet_keys", mode="before")
    @classmethod
    def parse_fernet_keys(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return json.loads(v)
        return v

    # Neo4j
    neo4j_uri: str = "neo4j+s://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # Rate Limiting
    rate_limit_default: str = "60/minute"
    rate_limit_ingest: str = "20/minute"

    # Sleep Cycle
    sleep_cron_hour: int = 2
    sleep_cron_minute: int = 0

    # Logging
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
