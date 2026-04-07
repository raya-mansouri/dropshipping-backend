"""add missing performance indexes

Revision ID: b2c3d4e5f7g
Revises: ca45d86f9f2f
Create Date: 2026-04-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f7g'
down_revision: Union[str, None] = 'ca45d86f9f2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Index for order_history queries by order_id (very frequent)
    op.create_index(
        'ix__order_history__order_id',
        'order_history',
        ['order_id'],
    )

    # Composite index for inventory reservation cleanup cron
    op.create_index(
        'ix__inventory_reservations__status_expires_at',
        'inventory_reservations',
        ['status', 'expires_at'],
    )

    # Index for supplier payout release cron
    op.create_index(
        'ix__supplier_payouts__status_dispute_window',
        'supplier_payouts',
        ['status', 'dispute_window_ends_at'],
    )

    # Index for order_items lookups by seller_listing_id
    op.create_index(
        'ix__order_items__seller_listing_id',
        'order_items',
        ['seller_listing_id'],
    )

    # Indexes for refunds lookups
    op.create_index(
        'ix__refunds__order_item_id',
        'refunds',
        ['order_item_id'],
    )
    op.create_index(
        'ix__refunds__payment_id',
        'refunds',
        ['payment_id'],
    )

    # Index for outgoing webhook log cleanup cron
    op.create_index(
        'ix__outgoing_webhook_logs__status_created_at',
        'outgoing_webhook_logs',
        ['status', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix__outgoing_webhook_logs__status_created_at', table_name='outgoing_webhook_logs')
    op.drop_index('ix__refunds__payment_id', table_name='refunds')
    op.drop_index('ix__refunds__order_item_id', table_name='refunds')
    op.drop_index('ix__order_items__seller_listing_id', table_name='order_items')
    op.drop_index('ix__supplier_payouts__status_dispute_window', table_name='supplier_payouts')
    op.drop_index('ix__inventory_reservations__status_expires_at', table_name='inventory_reservations')
    op.drop_index('ix__order_history__order_id', table_name='order_history')
