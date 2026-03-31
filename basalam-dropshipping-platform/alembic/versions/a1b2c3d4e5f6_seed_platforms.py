"""seed platforms table

Revision ID: a1b2c3d4e5f6
Revises: f800cd7fcfd7
Create Date: 2026-03-31 13:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from datetime import datetime
import uuid


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f800cd7fcfd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PLATFORMS = [
    {
        "code": "basalam",
        "name": "Basalam",
        "platform_type": "marketplace",
    },
    {
        "code": "shopify",
        "name": "Shopify",
        "platform_type": "seller_system",
    },
    {
        "code": "woocommerce",
        "name": "WooCommerce",
        "platform_type": "seller_system",
    },
]

# Deterministic UUIDs so the seed is idempotent
NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # dns namespace


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.utcnow()

    for platform in PLATFORMS:
        platform_id = str(uuid.uuid5(NAMESPACE, f"platform-{platform['code']}"))

        # Use INSERT ... ON CONFLICT DO NOTHING for idempotency
        conn.execute(text("""
            INSERT INTO platforms (id, code, name, platform_type, created_at, updated_at)
            VALUES (:id, :code, :name, :platform_type, :now, :now)
            ON CONFLICT (code) DO NOTHING
        """), {
            "id": platform_id,
            "code": platform["code"],
            "name": platform["name"],
            "platform_type": platform["platform_type"],
            "now": now,
        })


def downgrade() -> None:
    conn = op.get_bind()
    codes = [p["code"] for p in PLATFORMS]
    conn.execute(
        text("DELETE FROM platforms WHERE code = ANY(:codes)"),
        {"codes": codes},
    )
