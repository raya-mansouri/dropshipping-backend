"""create sync_states table

Revision ID: c3d4e5f6a7b8
Revises: f800cd7fcfd7
Create Date: 2026-04-01 16:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "f800cd7fcfd7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "integration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shop_integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="idle", nullable=False),
        sa.Column("sync_mode", sa.String(20), server_default="full", nullable=False),
        sa.Column("last_sync_timestamp", sa.DateTime(), nullable=True),
        sa.Column("cursor_token", sa.String(500), nullable=True),
        sa.Column("total_synced", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("integration_id", "entity_type", name="uq_sync_state_integration_entity"),
    )
    op.create_index("ix_sync_states_integration_id", "sync_states", ["integration_id"])


def downgrade() -> None:
    op.drop_index("ix_sync_states_integration_id", table_name="sync_states")
    op.drop_table("sync_states")
