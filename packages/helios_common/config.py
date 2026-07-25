"""Structured configuration loaded from the environment.

Every tunable lives here so that no module reaches for ``os.environ`` directly
and no credential is ever written into source. Defaults are chosen so that a
fresh checkout runs against the Docker Compose stack without a ``.env`` file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for every Helios process."""

    model_config = SettingsConfigDict(
        env_prefix="HELIOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False

    # ------------------------------------------------------------- database --
    database_url: str = "postgresql+psycopg://helios:helios@localhost:5432/helios"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_echo: bool = False

    # -------------------------------------------------------- evidence store --
    evidence_backend: Literal["filesystem", "s3"] = "filesystem"
    evidence_root: Path = Path("./data/evidence-store")
    evidence_bucket: str = "helios-evidence"
    s3_endpoint_url: str | None = None
    """Set to the MinIO endpoint for local development; ``None`` uses real AWS."""
    s3_region: str = "us-west-2"

    # ------------------------------------------------------------- ingestion --
    user_agent: str = (
        "ProjectHelios/0.1 (open public-infrastructure research; "
        "+https://github.com/project-helios/helios)"
    )
    """Identifies the crawler honestly, as required by our responsible-use policy."""

    http_timeout_seconds: float = 60.0
    http_max_retries: int = 4
    http_backoff_base_seconds: float = 1.0
    http_backoff_max_seconds: float = 60.0
    default_rate_limit_per_second: float = 2.0

    allow_live_fetch: bool = True
    """Master switch. Tests set this ``False`` so a stray connector cannot reach the network."""

    # ---------------------------------------------------------------- ethics --
    redact_natural_person_names: bool = True
    """Suppress owner names classified as private individuals before persistence."""

    redact_owner_mailing_addresses: bool = True

    # ----------------------------------------------------------------- study --
    study_region_slug: str = "east-valley-az"
    study_region_bbox: tuple[float, float, float, float] = (-111.98, 33.16, -111.35, 33.52)
    """(min_lon, min_lat, max_lon, max_lat) covering Mesa through Apache Junction."""

    # ------------------------------------------------------------------- api --
    api_title: str = "Helios Open AI Infrastructure Observatory API"
    api_version: str = "0.1.0"
    api_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    api_default_page_size: int = 50
    api_max_page_size: int = 500
    admin_api_token: str | None = None
    """Bearer token guarding ``/admin`` routes. Unset means admin routes are refused."""

    # --------------------------------------------------------------- logging --
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    @field_validator("evidence_root")
    @classmethod
    def _expand_evidence_root(cls, value: Path) -> Path:
        return value.expanduser()

    @property
    def sync_database_url(self) -> str:
        """Database URL guaranteed to use a synchronous driver."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that configuration is read once and shared. Tests clear the cache
    via ``get_settings.cache_clear()``.
    """
    return Settings()
