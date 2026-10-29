"""
HOOPCHAIN — Application Configuration
Reads from environment variables / .env file.
"""

from __future__ import annotations

import json
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://hoopchain:hoopchain_dev@localhost:5433/hoopchain"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Graph
    graph_pickle_path: str = "graph.pkl"
    use_mock_graph: bool = True  # True = use built-in mock graph; False = load real pickle

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174"]

    # Security
    api_secret_key: str = "dev-secret-key-change-in-production"

    # App
    environment: str = "development"
    app_version: str = "0.1.0"

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_db_scheme(cls, v: str) -> str:
        # Railway (and many PaaS) provide postgresql:// without the asyncpg driver suffix
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if isinstance(v, str) and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def graph_pickle_resolved(self) -> Path:
        """Resolve the graph pickle path relative to the backend directory."""
        p = Path(self.graph_pickle_path)
        if not p.is_absolute():
            p = Path(__file__).parent.parent / p
        return p.resolve()


settings = Settings()
