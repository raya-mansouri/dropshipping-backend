"""migrate monetary columns from numeric(12,2) to numeric(15,0) for toman

Revision ID: e5f6g7h8i9j
Revises: d4e5f7g8h9i
Create Date: 2026-04-15

Converts all monetary Numeric(12, 2) columns to Numeric(15, 0) to store
Iranian Toman as whole numbers (no fractional part).

Tables affected:
  - orders:       total_price, shipping_price, discount
  - order_items:  supplier_price, seller_price, shipping_price, profit
  - payments:     seller_paid_amount, supplier_payable_amount,
                  platform_fee, shipping_cost
  - refunds:      amount
  - supplier_payouts: amount
  - disputes:     outcome_amount
  - price_history: old_price, new_price, old_supplier_price, new_supplier_price
  - supplier_variants: cost_price
  - seller_variants:   price, custom_price

Existing data is rounded to the nearest integer via PostgreSQL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6g7h8i9j"
down_revision: Union[str, None] = "d4e5f7g8h9i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── orders ──
    op.alter_column("orders", "total_price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("orders", "shipping_price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("orders", "discount",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))

    # ── order_items ──
    op.alter_column("order_items", "supplier_price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("order_items", "seller_price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("order_items", "shipping_price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("order_items", "profit",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))

    # ── payments ──
    op.alter_column("payments", "seller_paid_amount",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("payments", "supplier_payable_amount",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("payments", "platform_fee",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("payments", "shipping_cost",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))

    # ── refunds ──
    op.alter_column("refunds", "amount",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))

    # ── supplier_payouts ──
    op.alter_column("supplier_payouts", "amount",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))

    # ── disputes ──
    op.alter_column("disputes", "outcome_amount",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))

    # ── price_history (table not yet created by any previous migration) ──
    op.create_table(
        "price_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.UUID(), nullable=False),
        sa.Column("listing_id", sa.UUID(), nullable=True),
        sa.Column("old_price", sa.Numeric(15, 0), nullable=False),
        sa.Column("new_price", sa.Numeric(15, 0), nullable=False),
        sa.Column("old_supplier_price", sa.Numeric(15, 0), nullable=True),
        sa.Column("new_supplier_price", sa.Numeric(15, 0), nullable=True),
        sa.Column("margin_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("margin_changed", sa.String(20), nullable=True),
        sa.Column("change_reason", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["supplier_variants.id"],
            name=op.f("fk__price_history__variant_id__supplier_variants"),
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["seller_listings.id"],
            name=op.f("fk__price_history__listing_id__seller_listings"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk__price_history")),
    )
    op.create_index("idx_price_history_variant", "price_history", ["variant_id"])
    op.create_index("idx_price_history_listing", "price_history", ["listing_id"])
    op.create_index("idx_price_history_created", "price_history", ["created_at"])

    # ── supplier_variants ──
    op.alter_column("supplier_variants", "cost_price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))

    # ── seller_variants ──
    op.alter_column("seller_variants", "price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("seller_variants", "custom_price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))


def downgrade() -> None:
    # ── seller_variants ──
    op.alter_column("seller_variants", "custom_price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("seller_variants", "price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))

    # ── supplier_variants ──
    op.alter_column("supplier_variants", "cost_price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))

    # ── price_history ──
    op.drop_index("idx_price_history_created", table_name="price_history")
    op.drop_index("idx_price_history_listing", table_name="price_history")
    op.drop_index("idx_price_history_variant", table_name="price_history")
    op.drop_table("price_history")

    # ── disputes ──
    op.alter_column("disputes", "outcome_amount",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))

    # ── supplier_payouts ──
    op.alter_column("supplier_payouts", "amount",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))

    # ── refunds ──
    op.alter_column("refunds", "amount",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))

    # ── payments ──
    op.alter_column("payments", "shipping_cost",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("payments", "platform_fee",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("payments", "supplier_payable_amount",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("payments", "seller_paid_amount",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))

    # ── order_items ──
    op.alter_column("order_items", "profit",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("order_items", "shipping_price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("order_items", "seller_price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("order_items", "supplier_price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))

    # ── orders ──
    op.alter_column("orders", "discount",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("orders", "shipping_price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("orders", "total_price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
