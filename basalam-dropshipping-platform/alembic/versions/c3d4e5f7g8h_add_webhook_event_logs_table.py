"""add webhook_event_logs table

Revision ID: c3d4e5f7g8h
Revises: b2c3d4e5f7g
Create Date: 2026-04-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "c3d4e5f7g8h"
down_revision: Union[str, None] = "b2c3d4e5f7g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_event_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("platform_id", sa.String(100), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("platform_id", "event_id", name="uq_webhook_event_logs_platform_event"),
    )
    op.create_index("ix_webhook_event_logs_platform", "webhook_event_logs", ["platform_id"])
    op.create_index("ix_webhook_event_logs_created", "webhook_event_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_webhook_event_logs_created")
    op.drop_index("ix_webhook_event_logs_platform")
    op.drop_table("webhook_event_logs")
