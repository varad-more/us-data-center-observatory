"""Alembic environment for Helios.

Two Helios-specific behaviours:

* PostGIS and pg_trgm are created before the first migration runs, because the
  initial schema declares geometry columns and a trigram index.
* GeoAlchemy2's internally managed objects (``spatial_ref_sys``, the geometry
  indexes it creates itself) are excluded from autogenerate so migrations do not
  churn on extension-owned tables.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from typing import Any

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import engine_from_config, pool, text

# Importing the models module registers every table on Base.metadata.
import helios_domain.models  # noqa: F401
from helios_common.config import get_settings
from helios_domain.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_EXCLUDED_TABLES = {"spatial_ref_sys", "geography_columns", "geometry_columns", "raster_columns"}


def _database_url() -> str:
    """Resolve the target database URL from the environment or settings."""
    return os.environ.get("HELIOS_DATABASE_URL") or get_settings().sync_database_url


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """Filter PostGIS-managed objects out of autogenerate."""
    if type_ == "table" and name in _EXCLUDED_TABLES:
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)  # type: ignore[no-any-return]


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        render_item=alembic_helpers.render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            render_item=alembic_helpers.render_item,
            process_revision_directives=alembic_helpers.writer,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
