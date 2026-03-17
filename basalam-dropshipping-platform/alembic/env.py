"""
Alembic Environment Configuration
===================================
Configures Alembic for async SQLAlchemy with asyncpg
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import all models from src.domains
from src.domains.accounts.models import User, Account, Role, UserRole, account_roles
from src.domains.shops.models import (
    Platform,
    Shop,
    ShopIntegration,
    SyncJob,
    ShippingMethod,
    SupplierShippingProfile,
)
from src.domains.products.models import (
    Category,
    SupplierProduct,
    ProductVariant,
    SupplierVariant,
    ProductMedia,
    SellerListing,
    SellerVariant,
)
from src.domains.orders.models import Order, OrderItem, OrderHistory, Shipment
from src.domains.payments.models import Payment, Refund, SupplierPayout, Dispute
from src.domains.inventory.models import (
    InventoryReservation,
    InventoryLog,
    InventoryReconciliation,
)
from src.domains.webhooks.models import (
    WebhookEvent,
    ProcessedEvent,
    WebhookRetrySchedule,
    WebhookDeadLetter,
)
from src.domains.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationLog,
)
from src.domains.integration_logs.models import IntegrationLog
from src.domains.product_validation.models import ProductValidationLog
from src.domains.system_logs.models import SystemLog
from src.domains.audit_logs.models import AuditLog
from src.domains.fraud_detection.models import FraudSignal
from src.core.database import Base

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata

# Database URL from config
# The URL should include 'postgresql+asyncpg://' prefix
sqlalchemy_url = config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async SQLAlchemy."""

    # Ensure URL uses postgresql+asyncpg
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
