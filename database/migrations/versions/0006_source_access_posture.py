"""move connector status and access limitation onto the source

Both were readable only through ``source_connectors``, and a row exists there
only when a registry entry names an importable connector. That inverted the
intent: the sources Helios *cannot* read have no connector, so the explanation
of what blocks them was the one thing the API dropped. Five of the six blocked
sources published no reason at all and reported themselves as "planned", which
reads as work not yet started rather than access denied.

Status and limitation are facts about the source, so they live on the source.
``source_connectors`` keeps what is genuinely connector runtime state.

Revision ID: b71e35c8a4d2
Revises: 4c1d90fb7a35
Create Date: 2026-07-28 11:05:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b71e35c8a4d2"
down_revision: str | None = "4c1d90fb7a35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column(
            "connector_status",
            sa.String(length=30),
            nullable=False,
            server_default="planned",
        ),
    )
    op.add_column("sources", sa.Column("access_limitation", sa.Text(), nullable=True))

    # Carry across what the connector rows already knew, so an existing database
    # does not have to wait for the next registry sync to tell the truth.
    op.execute("""
        UPDATE sources AS s
           SET connector_status = c.status,
               access_limitation = c.access_limitation
          FROM source_connectors AS c
         WHERE c.source_id = s.id
        """)


def downgrade() -> None:
    op.drop_column("sources", "access_limitation")
    op.drop_column("sources", "connector_status")
