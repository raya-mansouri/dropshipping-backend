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

    # ── price_history ──
    op.alter_column("price_history", "old_price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("price_history", "new_price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("price_history", "old_supplier_price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))
    op.alter_column("price_history", "new_supplier_price",
                    type_=sa.Numeric(15, 0), existing_type=sa.Numeric(12, 2))

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
    op.alter_column("price_history", "new_supplier_price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("price_history", "old_supplier_price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("price_history", "new_price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))
    op.alter_column("price_history", "old_price",
                    type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 0))

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
