"""Initial schema — campaign + all engine tables (slice 002-persistence-foundation).

Revision: 0001
Branch label: None
Parent: None

Creates all tables for slice 002. `account` and `session_lease` are intentionally
deferred to slice 004 (accounts-hardening-obs); campaign therefore has no account_id FK yet.

Tables created:
  campaign        — one playthrough; owns all engine rows below
  character_sheet — hero attributes; updated on every state change
  world           — current location, visited list, flags, turn counter
  event           — append-only hard-fact log; seq preserves insertion order
  combat          — transient in-progress fight (state is NULL between fights)
  archive_record  — immutable finished-run record (death/victory)
  save_slot       — named snapshots of the full campaign state
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # campaign — the top-level playthrough entity
    # Note: account_id FK is deferred to slice 004.
    # ------------------------------------------------------------------
    op.create_table(
        "campaign",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Narrative summary lives here — it is campaign-scoped, single value,
        # and not large enough to warrant a separate table.
        sa.Column("summary_text", sa.Text, nullable=False, server_default=""),
    )

    # ------------------------------------------------------------------
    # character_sheet — hero attributes (JSONB for full round-trip fidelity)
    # ------------------------------------------------------------------
    op.create_table(
        "character_sheet",
        sa.Column(
            "campaign_id",
            sa.Text,
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # Full Pydantic model_dump(mode="json") stored for exact round-trip.
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("alive", sa.Boolean, nullable=False, server_default="true"),
    )

    # ------------------------------------------------------------------
    # world — current location, visited list, flags, turn counter
    # ------------------------------------------------------------------
    op.create_table(
        "world",
        sa.Column(
            "campaign_id",
            sa.Text,
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("location", sa.Text, nullable=False, server_default=""),
        sa.Column("visited", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("flags", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("turn", sa.Integer, nullable=False, server_default="0"),
        # Full World snapshot for exact round-trip (includes known_npcs etc.)
        sa.Column("data", sa.JSON, nullable=False),
    )

    # ------------------------------------------------------------------
    # event — append-only chronological log
    # seq is computed as MAX(seq)+1 per campaign within the INSERT transaction.
    # UNIQUE(campaign_id, seq) prevents seq collisions.
    # ------------------------------------------------------------------
    op.create_table(
        "event",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Text,
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_unique_constraint("uq_event_campaign_seq", "event", ["campaign_id", "seq"])
    op.create_index("ix_event_campaign_seq", "event", ["campaign_id", "seq"])

    # ------------------------------------------------------------------
    # combat — transient in-progress fight; state is NULL between fights
    # ------------------------------------------------------------------
    op.create_table(
        "combat",
        sa.Column(
            "campaign_id",
            sa.Text,
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # NULL = no active fight; non-NULL = dict keyed by combat_id.
        # We store a dict {combat_id: <Combat JSON>} to support multiple concurrent
        # combats (the protocol allows load/save by combat_id).
        sa.Column("state", sa.JSON, nullable=True),
    )

    # ------------------------------------------------------------------
    # archive_record — immutable finished-run records (append-only)
    # ------------------------------------------------------------------
    op.create_table(
        "archive_record",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Text,
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # "graveyard" or "hall_of_fame"
        sa.Column("destination", sa.Text, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_archive_record_campaign", "archive_record", ["campaign_id", "destination"]
    )

    # ------------------------------------------------------------------
    # save_slot — named full-state snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "save_slot",
        sa.Column(
            "campaign_id",
            sa.Text,
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        # Full serialized snapshot: {character, world, events, summary, combats}
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("campaign_id", "name"),
    )


def downgrade() -> None:
    op.drop_table("save_slot")
    op.drop_index("ix_archive_record_campaign", table_name="archive_record")
    op.drop_table("archive_record")
    op.drop_table("combat")
    op.drop_index("ix_event_campaign_seq", table_name="event")
    op.drop_constraint("uq_event_campaign_seq", "event", type_="unique")
    op.drop_table("event")
    op.drop_table("world")
    op.drop_table("character_sheet")
    op.drop_table("campaign")
