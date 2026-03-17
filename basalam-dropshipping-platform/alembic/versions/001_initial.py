"""Initial migration - Create all tables

Revision ID: 001_initial
Revises:
Create Date: 2026-03-16

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================
    # ACCOUNTS DOMAIN
    # ============================================

    # Users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("phone", sa.String(20)),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_verified", sa.Boolean, default=False),
        sa.Column("role", sa.String(20), default="user"),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)

    # Accounts table
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("account_type", sa.String(20), nullable=False),
        sa.Column("business_name", sa.String(255)),
        sa.Column("business_id", sa.String(50)),
        sa.Column("status", sa.String(20), default="active"),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # Roles table
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255)),
        sa.Column("permissions", postgresql.JSONB, default=list),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_roles_name", "roles", ["name"], unique=True)

    # Account roles association table
    op.create_table(
        "account_roles",
        sa.Column(
            "account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id")
        ),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id")),
    )

    # User roles table
    op.create_table(
        "user_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # ============================================
    # SHOPS DOMAIN
    # ============================================

    # Platforms table
    op.create_table(
        "platforms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("platform_type", sa.String(50), nullable=False),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_platforms_code", "platforms", ["code"], unique=True)

    # Shops table
    op.create_table(
        "shops",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("shop_role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), default="active"),
        sa.Column("settings", postgresql.JSONB, default=dict),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_shops_account", "shops", ["account_id"])
    op.create_unique_constraint("uq_shop_account_name", "shops", ["account_id", "name"])

    # Shop integrations table
    op.create_table(
        "shop_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id"),
            nullable=False,
        ),
        sa.Column(
            "platform_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platforms.id"),
            nullable=False,
        ),
        sa.Column("external_shop_id", sa.String(255)),
        sa.Column("connection_type", sa.String(20), nullable=False),
        sa.Column("credentials_encrypted", postgresql.JSONB),
        sa.Column("webhook_id", sa.String(255)),
        sa.Column("status", sa.String(20), default="connected"),
        sa.Column("last_sync_started_at", sa.DateTime),
        sa.Column("last_synced_at", sa.DateTime),
        sa.Column("last_error", sa.String(1000)),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_platform_shop", "shop_integrations", ["platform_id", "external_shop_id"]
    )

    # Sync jobs table
    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "integration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shop_integrations.id"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(30), default="pending"),
        sa.Column("retry_count", sa.String(20), default=0),
        sa.Column("error_message", sa.String(2000)),
        sa.Column("scheduled_at", sa.DateTime),
        sa.Column("started_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # Shipping methods table
    op.create_table(
        "shipping_methods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "platform_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platforms.id")
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("shipping_type", sa.String(30), nullable=False),
        sa.Column("external_shipping_id", sa.String(255)),
        sa.Column("active", sa.Boolean, default=True),
        sa.Column("metadata", postgresql.JSONB, default=dict),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # Supplier shipping profiles table
    op.create_table(
        "supplier_shipping_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id"),
            nullable=False,
        ),
        sa.Column(
            "shipping_method_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shipping_methods.id"),
            nullable=False,
        ),
        sa.Column("cost", sa.String(20), nullable=False),
        sa.Column("free_shipping_threshold", sa.String(20)),
        sa.Column("regions", postgresql.JSONB, default=list),
        sa.Column("delivery_time_estimate", sa.String(20)),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # ============================================
    # PRODUCTS DOMAIN
    # ============================================

    # Categories table
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "platform_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platforms.id")
        ),
        sa.Column("external_category_id", sa.String(255)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id")
        ),
        sa.Column("franchise_percent", sa.Numeric(5, 2), default=0),
        sa.Column("is_forbidden", sa.Boolean, default=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # Supplier products table
    op.create_table(
        "supplier_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id"),
            nullable=False,
        ),
        sa.Column("external_product_id", sa.String(255)),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column(
            "category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id")
        ),
        sa.Column("has_variants", sa.Boolean, default=False),
        sa.Column("status", sa.String(30), default="active"),
        sa.Column("basalam_validation_error", postgresql.JSONB),
        sa.Column("raw_payload", postgresql.JSONB),
        sa.Column("moderation_status", sa.String(30)),
        sa.Column("last_synced_at", sa.DateTime),
        sa.Column("last_inventory_sync", sa.DateTime),
        sa.Column("last_price_sync", sa.DateTime),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_supplier_products_shop", "supplier_products", ["shop_id"])
    op.create_index(
        "idx_supplier_products_external", "supplier_products", ["external_product_id"]
    )
    op.create_index("idx_supplier_products_status", "supplier_products", ["status"])

    # Product variants table
    op.create_table(
        "product_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("supplier_products.id"),
            nullable=False,
        ),
        sa.Column("external_variant_id", sa.String(255)),
        sa.Column("sku", sa.String(100)),
        sa.Column("attributes", postgresql.JSONB, default=dict),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # Supplier variants table
    op.create_table(
        "supplier_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "supplier_product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("supplier_products.id"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id"),
            nullable=False,
        ),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("inventory", sa.Integer, default=0),
        sa.Column("reserved_inventory", sa.Integer, default=0),
        sa.Column("status", sa.String(20), default="active"),
        sa.Column("raw_payload", postgresql.JSONB),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # Product media table
    op.create_table(
        "product_media",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("supplier_products.id"),
            nullable=False,
        ),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("storage_provider", sa.String(50)),
        sa.Column("storage_key", sa.String(500)),
        sa.Column("hash", sa.String(64)),
        sa.Column("size_bytes", sa.Integer),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # Seller listings table
    op.create_table(
        "seller_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id"),
            nullable=False,
        ),
        sa.Column(
            "supplier_product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("supplier_products.id"),
            nullable=False,
        ),
        sa.Column("margin_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("custom_title", sa.String(500)),
        sa.Column("custom_description", sa.Text),
        sa.Column("custom_images", postgresql.JSONB, default=list),
        sa.Column("sync_enabled", sa.Boolean, default=True),
        sa.Column("sync_price", sa.Boolean, default=True),
        sa.Column("sync_inventory", sa.Boolean, default=True),
        sa.Column("status", sa.String(20), default="active"),
        sa.Column("view_count", sa.Integer, default=0),
        sa.Column("order_count", sa.Integer, default=0),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_seller_listings_shop", "seller_listings", ["shop_id"])
    op.create_index(
        "idx_seller_listings_supplier", "seller_listings", ["supplier_product_id"]
    )

    # Seller variants table
    op.create_table(
        "seller_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("seller_listings.id"),
            nullable=False,
        ),
        sa.Column(
            "supplier_variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("supplier_variants.id"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("inventory_cache", sa.Integer),
        sa.Column("custom_price", sa.Numeric(12, 2)),
        sa.Column("is_enabled", sa.Boolean, default=True),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # ============================================
    # ORDERS DOMAIN
    # ============================================

    # Orders table
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "platform_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platforms.id")
        ),
        sa.Column("external_order_id", sa.String(255)),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id"),
            nullable=False,
        ),
        sa.Column("customer_data", postgresql.JSONB, default=dict),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("shipping_price", sa.Numeric(12, 2), default=0),
        sa.Column("discount", sa.Numeric(12, 2), default=0),
        sa.Column("status", sa.String(30), default="pending"),
        sa.Column("notes", sa.Text),
        sa.Column("metadata", postgresql.JSONB, default=dict),
        sa.Column("confirmed_at", sa.DateTime),
        sa.Column("paid_at", sa.DateTime),
        sa.Column("shipped_at", sa.DateTime),
        sa.Column("delivered_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("cancelled_at", sa.DateTime),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_orders_shop", "orders", ["shop_id"])
    op.create_index("idx_orders_status", "orders", ["status"])
    op.create_index("idx_orders_external", "orders", ["external_order_id"])
    op.create_index("idx_orders_created", "orders", ["created_at"])

    # Order items table
    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id"),
            nullable=False,
        ),
        sa.Column(
            "supplier_shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id"),
            nullable=False,
        ),
        sa.Column(
            "seller_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("seller_listings.id"),
        ),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("supplier_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("seller_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("shipping_price", sa.Numeric(12, 2), default=0),
        sa.Column("profit", sa.Numeric(12, 2)),
        sa.Column("status", sa.String(30), default="pending"),
        sa.Column("reject_reason", sa.String(255)),
        sa.Column("rejected_at", sa.DateTime),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_order_items_order", "order_items", ["order_id"])
    op.create_index("idx_order_items_supplier", "order_items", ["supplier_shop_id"])
    op.create_index("idx_order_items_variant", "order_items", ["variant_id"])

    # Order history table
    op.create_table(
        "order_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id"),
            nullable=False,
        ),
        sa.Column(
            "order_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("order_items.id"),
        ),
        sa.Column("from_status", sa.String(30)),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("actor_type", sa.String(30)),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reason", sa.Text),
        sa.Column("metadata", postgresql.JSONB, default=dict),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # Shipments table
    op.create_table(
        "shipments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id"),
            nullable=False,
        ),
        sa.Column(
            "order_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("order_items.id"),
            nullable=False,
        ),
        sa.Column(
            "shipping_method_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shipping_methods.id"),
        ),
        sa.Column("tracking_code", sa.String(255)),
        sa.Column("carrier", sa.String(100)),
        sa.Column("status", sa.String(30), default="pending"),
        sa.Column("shipped_at", sa.DateTime),
        sa.Column("delivered_at", sa.DateTime),
        sa.Column("delivery_confirmed_at", sa.DateTime),
        sa.Column("delivery_confirmed_by", sa.String(20)),
        sa.Column("estimated_delivery", sa.DateTime),
        sa.Column("actual_delivery", sa.DateTime),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_shipments_order", "shipments", ["order_id"])
    op.create_index("idx_shipments_tracking", "shipments", ["tracking_code"])

    # ============================================
    # PAYMENTS DOMAIN
    # ============================================

    # Payments table
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id"),
            nullable=False,
        ),
        sa.Column(
            "order_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("order_items.id"),
        ),
        sa.Column("seller_paid_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("supplier_payable_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("platform_fee", sa.Numeric(12, 2), default=0),
        sa.Column("shipping_cost", sa.Numeric(12, 2), default=0),
        sa.Column("gateway", sa.String(50)),
        sa.Column("gateway_transaction_id", sa.String(255)),
        sa.Column("gateway_refund_id", sa.String(255)),
        sa.Column("status", sa.String(30), default="pending"),
        sa.Column("paid_at", sa.DateTime),
        sa.Column("escrow_started_at", sa.DateTime),
        sa.Column("supplier_paid_at", sa.DateTime),
        sa.Column("refunded_at", sa.DateTime),
        sa.Column("failure_reason", sa.Text),
        sa.Column("failure_code", sa.String(50)),
        sa.Column("metadata", postgresql.JSONB, default=dict),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_payments_order", "payments", ["order_id"])
    op.create_index("idx_payments_status", "payments", ["status"])
    op.create_index("idx_payments_gateway", "payments", ["gateway_transaction_id"])

    # Refunds table
    op.create_table(
        "refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("order_items.id"),
            nullable=False,
        ),
        sa.Column(
            "payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id")
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("refund_type", sa.String(20)),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.String(30), default="requested"),
        sa.Column("requested_by", sa.String(20)),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True)),
        sa.Column("rejected_by", postgresql.UUID(as_uuid=True)),
        sa.Column("approved_at", sa.DateTime),
        sa.Column("rejected_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("gateway_refund_id", sa.String(255)),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # Supplier payouts table
    op.create_table(
        "supplier_payouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id"),
            nullable=False,
        ),
        sa.Column(
            "order_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("order_items.id"),
            nullable=False,
        ),
        sa.Column(
            "payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id")
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(30), default="pending"),
        sa.Column("release_conditions_met", sa.Boolean, default=False),
        sa.Column("delivery_confirmed_at", sa.DateTime),
        sa.Column("dispute_window_ends_at", sa.DateTime),
        sa.Column("payout_method", sa.String(50)),
        sa.Column("payout_reference", sa.String(255)),
        sa.Column("released_at", sa.DateTime),
        sa.Column("failed_at", sa.DateTime),
        sa.Column("failure_reason", sa.Text),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # Disputes table
    op.create_table(
        "disputes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("order_items.id"),
            nullable=False,
        ),
        sa.Column("opened_by", sa.String(20), nullable=False),
        sa.Column("opened_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("evidence", postgresql.JSONB, default=list),
        sa.Column("status", sa.String(30), default="open"),
        sa.Column("resolution", sa.Text),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True)),
        sa.Column("resolved_at", sa.DateTime),
        sa.Column("outcome", sa.String(30)),
        sa.Column("outcome_amount", sa.Numeric(12, 2)),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_disputes_order_item", "disputes", ["order_item_id"])
    op.create_index("idx_disputes_status", "disputes", ["status"])

    # ============================================
    # INVENTORY DOMAIN
    # ============================================

    # Inventory reservations table
    op.create_table(
        "inventory_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("supplier_variants.id"),
            nullable=False,
        ),
        sa.Column(
            "order_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("order_items.id"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), default="reserved"),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("released_at", sa.DateTime),
        sa.Column("released_reason", sa.String(50)),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(
        "idx_inventory_reservations_variant", "inventory_reservations", ["variant_id"]
    )
    op.create_index(
        "idx_inventory_reservations_expires", "inventory_reservations", ["expires_at"]
    )
    op.create_index(
        "idx_inventory_reservations_order_item",
        "inventory_reservations",
        ["order_item_id"],
    )

    # Inventory logs table
    op.create_table(
        "inventory_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("supplier_variants.id"),
            nullable=False,
        ),
        sa.Column("old_inventory", sa.Integer, nullable=False),
        sa.Column("new_inventory", sa.Integer, nullable=False),
        sa.Column("change", sa.Integer, nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reference_type", sa.String(50)),
        sa.Column("reason", sa.Text),
        sa.Column("metadata", postgresql.JSONB, default=dict),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_inventory_logs_variant", "inventory_logs", ["variant_id"])
    op.create_index("idx_inventory_logs_created", "inventory_logs", ["created_at"])

    # Inventory reconciliations table
    op.create_table(
        "inventory_reconciliations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "integration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shop_integrations.id"),
        ),
        sa.Column("status", sa.String(30), default="pending"),
        sa.Column("total_variants", sa.Integer, default=0),
        sa.Column("matched_count", sa.Integer, default=0),
        sa.Column("mismatch_count", sa.Integer, default=0),
        sa.Column("fixed_count", sa.Integer, default=0),
        sa.Column("started_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("errors", postgresql.JSONB, default=list),
        sa.Column("details", postgresql.JSONB, default=list),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )

    # ============================================
    # WEBHOOKS DOMAIN
    # ============================================

    # Webhook events table
    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "platform_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platforms.id"),
            nullable=False,
        ),
        sa.Column(
            "integration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shop_integrations.id"),
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("external_event_id", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("signature", sa.String(255)),
        sa.Column("signature_verified", sa.Boolean, default=False),
        sa.Column("status", sa.String(30), default="received"),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("max_retries", sa.Integer, default=5),
        sa.Column("error_message", sa.Text),
        sa.Column("error_trace", sa.Text),
        sa.Column("processed_at", sa.DateTime),
        sa.Column("entity_type", sa.String(50)),
        sa.Column("entity_id", sa.String(255)),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_webhook_events_platform", "webhook_events", ["platform_id"])
    op.create_index("idx_webhook_events_type", "webhook_events", ["event_type"])
    op.create_index("idx_webhook_events_status", "webhook_events", ["status"])
    op.create_index(
        "idx_webhook_events_entity", "webhook_events", ["entity_type", "entity_id"]
    )
    op.create_unique_constraint(
        "uq_webhook_platform_event",
        "webhook_events",
        ["platform_id", "external_event_id"],
    )

    # Processed events table
    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("event_hash", sa.String(64)),
        sa.Column(
            "platform_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platforms.id"),
            nullable=False,
        ),
        sa.Column(
            "processed_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("processed_by", sa.String(50), default="webhook_processor"),
    )
    op.create_index(
        "idx_processed_events_platform", "processed_events", ["platform_id"]
    )

    # Webhook retry schedules table
    op.create_table(
        "webhook_retry_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "webhook_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_events.id"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("scheduled_at", sa.DateTime, nullable=False),
        sa.Column("executed_at", sa.DateTime),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("error", sa.Text),
    )
    op.create_index(
        "idx_webhook_retry_schedules_event",
        "webhook_retry_schedules",
        ["webhook_event_id"],
    )
    op.create_index(
        "idx_webhook_retry_schedules_scheduled",
        "webhook_retry_schedules",
        ["scheduled_at"],
    )

    # Webhook dead letter table
    op.create_table(
        "webhook_dead_letter",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "webhook_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_events.id"),
            nullable=False,
        ),
        sa.Column("original_event_type", sa.String(100)),
        sa.Column("payload", postgresql.JSONB),
        sa.Column("failure_reason", sa.Text, nullable=False),
        sa.Column("failure_count", sa.Integer, default=0),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True)),
        sa.Column("resolution_notes", sa.Text),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_webhook_dead_letter_status", "webhook_dead_letter", ["status"])

    # ============================================
    # NOTIFICATIONS DOMAIN
    # ============================================

    # Notifications table
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("action_url", sa.String(500)),
        sa.Column("action_type", sa.String(50)),
        sa.Column("payload", postgresql.JSONB, default=dict),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("read_at", sa.DateTime),
        sa.Column("read_by", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_notifications_user", "notifications", ["user_id"])
    op.create_index("idx_notifications_status", "notifications", ["status"])
    op.create_index("idx_notifications_type", "notifications", ["type"])

    # Notification preferences table
    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("email_enabled", sa.Boolean, default=True),
        sa.Column("sms_enabled", sa.Boolean, default=False),
        sa.Column("in_app_enabled", sa.Boolean, default=True),
        sa.Column("webhook_enabled", sa.Boolean, default=False),
        sa.Column("quiet_hours_enabled", sa.Boolean, default=False),
        sa.Column("quiet_hours_start", sa.String(5)),
        sa.Column("quiet_hours_end", sa.String(5)),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_user_event_preference",
        "notification_preferences",
        ["user_id", "event_type"],
    )

    # Notification logs table
    op.create_table(
        "notification_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.id"),
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("recipient", sa.String(255)),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("provider", sa.String(50)),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("error", sa.Text),
        sa.Column("error_code", sa.String(50)),
        sa.Column("sent_at", sa.DateTime),
        sa.Column("delivered_at", sa.DateTime),
        sa.Column("cost", sa.Numeric(10, 2)),
    )
    op.create_index(
        "idx_notification_logs_notification", "notification_logs", ["notification_id"]
    )
    op.create_index("idx_notification_logs_status", "notification_logs", ["status"])

    # ============================================
    # INTEGRATION LOGS DOMAIN
    # ============================================

    # Integration logs table
    op.create_table(
        "integration_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "integration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shop_integrations.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("request_data", postgresql.JSONB, default=dict),
        sa.Column("response_data", postgresql.JSONB, default=dict),
        sa.Column("error_message", sa.Text),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(
        "idx_integration_logs_integration", "integration_logs", ["integration_id"]
    )
    op.create_index("idx_integration_logs_action", "integration_logs", ["action"])
    op.create_index("idx_integration_logs_status", "integration_logs", ["status"])
    op.create_index("idx_integration_logs_created", "integration_logs", ["created_at"])

    # ============================================
    # PRODUCT VALIDATION DOMAIN
    # ============================================

    # Product validation logs table
    op.create_table(
        "product_validation_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "supplier_product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("supplier_products.id"),
            nullable=False,
        ),
        sa.Column("validation_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(50)),
        sa.Column("error_message", sa.Text),
        sa.Column("metadata", postgresql.JSONB, default=dict),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(
        "idx_product_validation_product",
        "product_validation_logs",
        ["supplier_product_id"],
    )
    op.create_index(
        "idx_product_validation_type", "product_validation_logs", ["validation_type"]
    )
    op.create_index(
        "idx_product_validation_status", "product_validation_logs", ["status"]
    )
    op.create_index(
        "idx_product_validation_created", "product_validation_logs", ["created_at"]
    )

    # ============================================
    # SYSTEM LOGS DOMAIN
    # ============================================

    # System logs table
    op.create_table(
        "system_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("service", sa.String(50), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("metadata", postgresql.JSONB, default=dict),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_system_logs_level", "system_logs", ["level"])
    op.create_index("idx_system_logs_service", "system_logs", ["service"])
    op.create_index("idx_system_logs_created", "system_logs", ["created_at"])

    # ============================================
    # AUDIT LOGS DOMAIN
    # ============================================

    # Audit logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("old_value", postgresql.JSONB, default=dict),
        sa.Column("new_value", postgresql.JSONB, default=dict),
        sa.Column("reason", sa.Text),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("idx_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("idx_audit_logs_action", "audit_logs", ["action"])
    op.create_index("idx_audit_logs_actor", "audit_logs", ["actor_type", "actor_id"])
    op.create_index("idx_audit_logs_created", "audit_logs", ["created_at"])

    # ============================================
    # FRAUD DETECTION DOMAIN
    # ============================================

    # Fraud signals table
    op.create_table(
        "fraud_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("data", postgresql.JSONB, default=dict),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime),
    )
    op.create_index(
        "idx_fraud_signals_entity", "fraud_signals", ["entity_type", "entity_id"]
    )
    op.create_index("idx_fraud_signals_type", "fraud_signals", ["signal_type"])
    op.create_index("idx_fraud_signals_severity", "fraud_signals", ["severity"])
    op.create_index("idx_fraud_signals_status", "fraud_signals", ["status"])
    op.create_index("idx_fraud_signals_created", "fraud_signals", ["created_at"])


def downgrade() -> None:
    # Drop all tables in reverse order (respecting foreign keys)

    # Fraud detection
    op.drop_table("fraud_signals")

    # Audit logs
    op.drop_table("audit_logs")

    # System logs
    op.drop_table("system_logs")

    # Product validation
    op.drop_table("product_validation_logs")

    # Integration logs
    op.drop_table("integration_logs")

    # Notifications
    op.drop_table("notification_logs")
    op.drop_table("notification_preferences")
    op.drop_table("notifications")

    # Webhooks
    op.drop_table("webhook_dead_letter")
    op.drop_table("webhook_retry_schedules")
    op.drop_table("processed_events")
    op.drop_table("webhook_events")

    # Inventory
    op.drop_table("inventory_reconciliations")
    op.drop_table("inventory_logs")
    op.drop_table("inventory_reservations")

    # Payments
    op.drop_table("disputes")
    op.drop_table("supplier_payouts")
    op.drop_table("refunds")
    op.drop_table("payments")

    # Orders
    op.drop_table("shipments")
    op.drop_table("order_history")
    op.drop_table("order_items")
    op.drop_table("orders")

    # Products
    op.drop_table("seller_variants")
    op.drop_table("seller_listings")
    op.drop_table("product_media")
    op.drop_table("supplier_variants")
    op.drop_table("product_variants")
    op.drop_table("supplier_products")
    op.drop_table("categories")

    # Shops
    op.drop_table("supplier_shipping_profiles")
    op.drop_table("shipping_methods")
    op.drop_table("sync_jobs")
    op.drop_table("shop_integrations")
    op.drop_table("shops")
    op.drop_table("platforms")

    # Accounts
    op.drop_table("user_roles")
    op.drop_table("account_roles")
    op.drop_table("roles")
    op.drop_table("accounts")
    op.drop_table("users")
