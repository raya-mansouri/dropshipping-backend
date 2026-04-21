"""replace shop_integration unique constraint with partial index

Revises: 6e3e6e1bf466
Create Date: 2026-04-21 12:00:00.000000

The old uq_shop_integration_shop constraint was a full UNIQUE on shop_id,
which blocked creating new integrations after disconnecting (the old
disconnected row still occupied the slot).  Replace it with a partial
unique index that only fires when status IN ('connected', 'error'),
matching the application-level BLOCKING_STATUSES check.
"""

from alembic import op
from sqlalchemy import text

revision = "a1b2c3d4e5f6"
down_revision = "6e3e6e1bf466"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_shop_integration_shop", "shop_integrations", type_="unique")
    op.execute(
        text(
            """
            CREATE UNIQUE INDEX one_active_integration_per_shop
            ON shop_integrations (shop_id)
            WHERE status IN ('connected', 'error')
            """
        )
    )


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS one_active_integration_per_shop"))
    op.create_unique_constraint(
        "uq_shop_integration_shop", "shop_integrations", ["shop_id"]
    )
