"""
Shops Domain Models
==================
Platforms, shops, and integrations

IMPORTANT: shop_role is ONLY 'supplier' OR 'seller' (not both) per a.md
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid


class Platform(Base, UUIDMixin, TimestampMixin):
    """
    Supported platforms (Basalam, Shopify, WooCommerce, etc.)
    
    Each platform has specific API and integration requirements
    """
    __tablename__ = "platforms"
    
    code = Column(String(50), unique=True, nullable=False, index=True)  # basalam, shopify, woocommerce
    name = Column(String(255), nullable=False)
    platform_type = Column(String(50), nullable=False)  # marketplace, seller_system, supplier_system
    
    # Relationships
    integrations = relationship("ShopIntegration", back_populates="platform")
    shipping_methods = relationship("ShippingMethod", back_populates="platform")


class Shop(Base, UUIDMixin, TimestampMixin):
    """
    Business shop
    
    IMPORTANT: shop_role is ONLY 'supplier' OR 'seller' (not both)
    Per a.md requirement - cannot be both
    """
    __tablename__ = "shops"
    
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    name = Column(String(255), nullable=False)
    shop_role = Column(String(20), nullable=False)  # 'supplier' OR 'seller' ONLY
    status = Column(String(20), default="active")  # active, disabled
    settings = Column(JSONB, default=dict)  # Shop-specific settings
    
    # Relationships
    account = relationship("Account", back_populates="shops")
    integrations = relationship("ShopIntegration", back_populates="shop", cascade="all, delete-orphan")
    supplier_products = relationship("SupplierProduct", back_populates="shop")
    seller_listings = relationship("SellerListing", back_populates="shop")
    orders = relationship("Order", back_populates="shop")
    
    __table_args__ = (
        UniqueConstraint('account_id', 'name', name='uq_shop_account_name'),
    )


class ShopIntegration(Base, UUIDMixin, TimestampMixin):
    """
    Integration connection to external platform
    
    Stores OAuth tokens, API keys, and connection status
    """
    __tablename__ = "shop_integrations"
    
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    platform_id = Column(UUID(as_uuid=True), ForeignKey("platforms.id"), nullable=False)
    external_shop_id = Column(String(255))  # ID on external platform
    
    connection_type = Column(String(20), nullable=False)  # oauth, api, token, manual
    credentials_encrypted = Column(JSONB)  # Encrypted tokens/keys
    webhook_id = Column(String(255))  # Registered webhook ID on platform
    
    status = Column(String(20), default="connected")  # connected, disconnected, error
    last_sync_started_at = Column(DateTime)
    last_synced_at = Column(DateTime)
    last_error = Column(String(1000))
    
    # Relationships
    shop = relationship("Shop", back_populates="integrations")
    platform = relationship("Platform", back_populates="integrations")
    sync_jobs = relationship("SyncJob", back_populates="integration")
    
    __table_args__ = (
        UniqueConstraint('platform_id', 'external_shop_id', name='uq_platform_shop'),
    )


class SyncJob(Base, UUIDMixin, TimestampMixin):
    """
    Sync job tracking
    
    Tracks sync operations for each integration
    """
    __tablename__ = "sync_jobs"
    
    integration_id = Column(UUID(as_uuid=True), ForeignKey("shop_integrations.id"), nullable=False)
    entity_type = Column(String(50), nullable=False)  # product, inventory, order
    entity_id = Column(UUID(as_uuid=True))
    
    status = Column(String(30), default="pending")  # pending, running, completed, failed
    retry_count = Column(String(20), default=0)
    error_message = Column(String(2000))
    
    scheduled_at = Column(DateTime)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Relationships
    integration = relationship("ShopIntegration", back_populates="sync_jobs")


class ShippingMethod(Base, UUIDMixin, TimestampMixin):
    """
    Available shipping methods per platform
    """
    __tablename__ = "shipping_methods"
    
    platform_id = Column(UUID(as_uuid=True), ForeignKey("platforms.id"))
    name = Column(String(255), nullable=False)
    shipping_type = Column(String(30), nullable=False)  # vendor, platform, third_party, express, pickup
    external_shipping_id = Column(String(255))
    active = Column(Boolean, default=True)
    extra_data = Column("metadata", JSONB, default=dict)
    
    # Relationships
    platform = relationship("Platform", back_populates="shipping_methods")
    profiles = relationship("SupplierShippingProfile", back_populates="shipping_method")


class SupplierShippingProfile(Base, UUIDMixin, TimestampMixin):
    """
    Supplier-specific shipping configuration
    """
    __tablename__ = "supplier_shipping_profiles"
    
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    shipping_method_id = Column(UUID(as_uuid=True), ForeignKey("shipping_methods.id"), nullable=False)
    
    cost = Column(String(20), nullable=False)  # Can be formula like "base + weight * 100"
    free_shipping_threshold = Column(String(20))  # Free shipping above this amount
    regions = Column(JSONB, default=list)  # ["Tehran", "Alborz"]
    delivery_time_estimate = Column(String(20))  # "24-48", "3-5 days"
    is_active = Column(Boolean, default=True)
    
    # Relationships
    shipping_method = relationship("ShippingMethod", back_populates="profiles")
