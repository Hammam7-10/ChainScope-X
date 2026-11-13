"""Environment-backed configuration for local R5 database adapters."""
from __future__ import annotations

import os
from dataclasses import dataclass


class DatabaseConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseConfig:
    postgres_dsn: str
    mongodb_uri: str
    mongodb_database: str

    @classmethod
    def from_environment(cls) -> "DatabaseConfig":
        postgres_dsn = os.getenv("CHAIN_SCOPE_POSTGRES_DSN", "").strip()
        mongodb_uri = os.getenv("CHAIN_SCOPE_MONGODB_URI", "").strip()
        mongodb_database = os.getenv("CHAIN_SCOPE_MONGODB_DATABASE", "chainscope").strip()
        if not postgres_dsn or not mongodb_uri:
            missing = []
            if not postgres_dsn:
                missing.append("CHAIN_SCOPE_POSTGRES_DSN")
            if not mongodb_uri:
                missing.append("CHAIN_SCOPE_MONGODB_URI")
            raise DatabaseConfigurationError("Missing database configuration: " + ", ".join(missing))
        if not mongodb_database or len(mongodb_database) > 63:
            raise DatabaseConfigurationError("Invalid MongoDB database name")
        if postgres_dsn.startswith("postgresql://"):
            postgres_dsn = "postgresql+asyncpg://" + postgres_dsn[len("postgresql://"):]
        if not postgres_dsn.startswith("postgresql+asyncpg://"):
            raise DatabaseConfigurationError("PostgreSQL DSN must use PostgreSQL asyncpg")
        return cls(postgres_dsn, mongodb_uri, mongodb_database)
