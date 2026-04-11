"""convert all datetime columns to timestamptz

Revision ID: d4e5f7g8h9i
Revises: c3d4e5f7g8h
Create Date: 2026-04-11

Converts all TIMESTAMP columns to TIMESTAMPTZ across the entire database.
Includes domain-specific datetime columns and TimestampMixin created_at/updated_at.
Existing UTC values are preserved — no data conversion needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f7g8h9i"
down_revision: Union[str, None] = "c3d4e5f7g8h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── created_at / updated_at on all TimestampMixin tables ──

    ts_mixin_tables = [
        "accounts",
        "audit_logs",
        "categories",
        "disputes",
        "forbidden_keywords",
        "forbidden_product_rules",
        "fraud_signals",
        "integration_logs",
        "inventory_reconciliations",
        "inventory_reservations",
        "notification_preferences",
        "notifications",
        "order_items",
        "orders",
        "outgoing_webhook_dlq",
        "outgoing_webhook_logs",
        "payments",
        "platforms",
        "product_media",
        "product_validation_logs",
        "product_variants",
        "refunds",
        "roles",
        "seller_listings",
        "seller_variants",
        "shipments",
        "shipping_methods",
        "shop_integrations",
        "shops",
        "supplier_payouts",
        "supplier_products",
        "supplier_shipping_profiles",
        "supplier_variants",
        "sync_jobs",
        "sync_states",
        "system_logs",
        "user_roles",
        "users",
        "webhook_dead_letter",
        "webhook_event_logs",
        "webhook_events",
    ]

    for table in ts_mixin_tables:
        op.alter_column(table, "created_at",
                        existing_type=sa.DateTime(),
                        type_=sa.DateTime(timezone=True),
                        existing_nullable=False)
        op.alter_column(table, "updated_at",
                        existing_type=sa.DateTime(),
                        type_=sa.DateTime(timezone=True),
                        existing_nullable=False)

    # ── Domain-specific datetime columns ──

    # webhook_event_logs
    op.alter_column("webhook_event_logs", "processed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # webhook_events
    op.alter_column("webhook_events", "processed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # processed_events
    op.alter_column("processed_events", "processed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)

    # webhook_retry_schedules
    op.alter_column("webhook_retry_schedules", "scheduled_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("webhook_retry_schedules", "executed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # outgoing_webhook_logs
    op.alter_column("outgoing_webhook_logs", "last_attempt_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("outgoing_webhook_logs", "next_retry_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # outgoing_webhook_dlq
    op.alter_column("outgoing_webhook_dlq", "resolved_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # shop_integrations
    op.alter_column("shop_integrations", "webhook_registered_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("shop_integrations", "webhook_secret_rotated_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("shop_integrations", "webhook_previous_secret_expires_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("shop_integrations", "last_sync_started_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("shop_integrations", "last_synced_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # sync_jobs
    op.alter_column("sync_jobs", "scheduled_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("sync_jobs", "started_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("sync_jobs", "completed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # sync_states
    op.alter_column("sync_states", "last_sync_timestamp",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # inventory_reservations
    op.alter_column("inventory_reservations", "expires_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
    op.alter_column("inventory_reservations", "released_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # inventory_logs
    op.alter_column("inventory_logs", "created_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)

    # inventory_reconciliations
    op.alter_column("inventory_reconciliations", "started_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("inventory_reconciliations", "completed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # notifications
    op.alter_column("notifications", "read_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # notification_logs
    op.alter_column("notification_logs", "sent_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("notification_logs", "delivered_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # system_logs (created_at handled by ts_mixin_tables loop)

    # payments
    op.alter_column("payments", "paid_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("payments", "escrow_started_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("payments", "supplier_paid_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("payments", "refunded_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # refunds
    op.alter_column("refunds", "approved_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("refunds", "rejected_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("refunds", "completed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # supplier_payouts
    op.alter_column("supplier_payouts", "delivery_confirmed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("supplier_payouts", "dispute_window_ends_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("supplier_payouts", "released_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("supplier_payouts", "failed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # disputes
    op.alter_column("disputes", "resolved_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # orders
    op.alter_column("orders", "confirmed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("orders", "paid_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("orders", "shipped_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("orders", "delivered_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("orders", "completed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("orders", "cancelled_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # order_items
    op.alter_column("order_items", "rejected_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # order_history
    op.alter_column("order_history", "created_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)

    # shipments
    op.alter_column("shipments", "shipped_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("shipments", "delivered_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("shipments", "delivery_confirmed_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("shipments", "estimated_delivery",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("shipments", "actual_delivery",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # supplier_products
    op.alter_column("supplier_products", "last_synced_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("supplier_products", "last_inventory_sync",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("supplier_products", "last_price_sync",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)

    # fraud_signals (created_at handled by ts_mixin_tables loop)
    op.alter_column("fraud_signals", "resolved_at",
                    existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)


def downgrade() -> None:
    # NOTE: Downgrade converts TIMESTAMPTZ back to TIMESTAMP.
    # This strips timezone info. Only safe if all values are UTC.

    # ── created_at / updated_at on all TimestampMixin tables ──

    ts_mixin_tables = [
        "accounts",
        "audit_logs",
        "categories",
        "disputes",
        "forbidden_keywords",
        "forbidden_product_rules",
        "fraud_signals",
        "integration_logs",
        "inventory_reconciliations",
        "inventory_reservations",
        "notification_preferences",
        "notifications",
        "order_items",
        "orders",
        "outgoing_webhook_dlq",
        "outgoing_webhook_logs",
        "payments",
        "platforms",
        "product_media",
        "product_validation_logs",
        "product_variants",
        "refunds",
        "roles",
        "seller_listings",
        "seller_variants",
        "shipments",
        "shipping_methods",
        "shop_integrations",
        "shops",
        "supplier_payouts",
        "supplier_products",
        "supplier_shipping_profiles",
        "supplier_variants",
        "sync_jobs",
        "sync_states",
        "system_logs",
        "user_roles",
        "users",
        "webhook_dead_letter",
        "webhook_event_logs",
        "webhook_events",
    ]

    for table in ts_mixin_tables:
        op.alter_column(table, "created_at",
                        existing_type=sa.DateTime(timezone=True),
                        type_=sa.DateTime(), existing_nullable=False)
        op.alter_column(table, "updated_at",
                        existing_type=sa.DateTime(timezone=True),
                        type_=sa.DateTime(), existing_nullable=False)

    # ── Domain-specific datetime columns (reverse order) ──

    op.alter_column("fraud_signals", "resolved_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("supplier_products", "last_synced_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("supplier_products", "last_inventory_sync",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("supplier_products", "last_price_sync",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("shipments", "shipped_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("shipments", "delivered_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("shipments", "delivery_confirmed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("shipments", "estimated_delivery",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("shipments", "actual_delivery",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("order_history", "created_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)

    op.alter_column("order_items", "rejected_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("orders", "confirmed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("orders", "paid_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("orders", "shipped_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("orders", "delivered_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("orders", "completed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("orders", "cancelled_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("disputes", "resolved_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("supplier_payouts", "delivery_confirmed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("supplier_payouts", "dispute_window_ends_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("supplier_payouts", "released_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("supplier_payouts", "failed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("refunds", "approved_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("refunds", "rejected_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("refunds", "completed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("payments", "paid_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("payments", "escrow_started_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("payments", "supplier_paid_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("payments", "refunded_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("notification_logs", "sent_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("notification_logs", "delivered_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("notifications", "read_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("inventory_reconciliations", "started_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("inventory_reconciliations", "completed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("inventory_logs", "created_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)

    op.alter_column("inventory_reservations", "expires_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
    op.alter_column("inventory_reservations", "released_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("sync_states", "last_sync_timestamp",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("sync_jobs", "scheduled_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("sync_jobs", "started_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("sync_jobs", "completed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("shop_integrations", "webhook_registered_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("shop_integrations", "webhook_secret_rotated_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("shop_integrations", "webhook_previous_secret_expires_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("shop_integrations", "last_sync_started_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("shop_integrations", "last_synced_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("outgoing_webhook_dlq", "resolved_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("outgoing_webhook_logs", "last_attempt_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("outgoing_webhook_logs", "next_retry_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("webhook_retry_schedules", "scheduled_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
    op.alter_column("webhook_retry_schedules", "executed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("processed_events", "processed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)

    op.alter_column("webhook_events", "processed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)

    op.alter_column("webhook_event_logs", "processed_at",
                    existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
