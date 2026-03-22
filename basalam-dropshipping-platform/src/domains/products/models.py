"""
Products Domain Models
======================
Products, variants, categories, and media

Handles:
- Supplier products (from Basalam)
- Platform products (normalized)
- Seller listings (what sellers offer)
- Categories with franchise rules
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Numeric, Integer, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid


class Category(Base, UUIDMixin, TimestampMixin):
    """
    Product categories with franchise/margin rules
    
    Each category can have minimum margin requirements from Basalam
    """
    __tablename__ = "categories"
    
    platform_id = Column(UUID(as_uuid=True), ForeignKey("platforms.id"))
    external_category_id = Column(String(255))  # Basalam category ID
    name = Column(String(255), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"))
    
    franchise_percent = Column(Numeric(5, 2), default=0)  # Minimum margin for this category
    is_forbidden = Column(Boolean, default=False)  # Category is prohibited
    is_active = Column(Boolean, default=True)
    
    # Relationships
    parent = relationship("Category", remote_side="Category.id", backref="children")
    products = relationship("SupplierProduct", back_populates="category")


class SupplierProduct(Base, UUIDMixin, TimestampMixin):
    """
    Product from supplier (Basalam)
    
    Source of truth for product data
    """
    __tablename__ = "supplier_products"
    
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    external_product_id = Column(String(255))  # Basalam product ID
    
    title = Column(String(500), nullable=False)
    description = Column(Text)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"))
    
    has_variants = Column(Boolean, default=False)
    status = Column(String(30), default="active")  # active, archived, forbidden, pending_review, needs_revision
    
    # Basalam-specific
    basalam_validation_error = Column(JSONB)  # Error from Basalam if forbidden
    raw_payload = Column(JSONB)  # Original data from Basalam
    moderation_status = Column(String(30))  # pending, approved, rejected
    
    last_synced_at = Column(DateTime)
    last_inventory_sync = Column(DateTime)
    last_price_sync = Column(DateTime)
    
    # Relationships
    shop = relationship("Shop", back_populates="supplier_products")
    category = relationship("Category", back_populates="products")
    variants = relationship("SupplierVariant", back_populates="product", cascade="all, delete-orphan")
    images = relationship("ProductMedia", back_populates="product", cascade="all, delete-orphan")
    seller_listings = relationship("SellerListing", back_populates="supplier_product")
    
    __table_args__ = (
        Index('idx_supplier_products_shop', 'shop_id'),
        Index('idx_supplier_products_external', 'external_product_id'),
        Index('idx_supplier_products_status', 'status'),
    )


class ProductVariant(Base, UUIDMixin, TimestampMixin):
    """
    Base variant definition
    
    A variant belongs to a product (e.g., Red/L, Blue/M)
    """
    __tablename__ = "product_variants"
    
    product_id = Column(UUID(as_uuid=True), ForeignKey("supplier_products.id"), nullable=False)
    external_variant_id = Column(String(255))  # Basalam variant ID
    
    sku = Column(String(100))
    attributes = Column(JSONB, default=dict)  # {"color": "red", "size": "XL"}
    
    # Relationships
    product = relationship("SupplierProduct", back_populates="variants")
    supplier_variants = relationship("SupplierVariant", back_populates="variant")
    order_items = relationship("OrderItem", back_populates="variant")


class SupplierVariant(Base, UUIDMixin, TimestampMixin):
    """
    Supplier-specific variant data
    
    Contains price and inventory for each variant
    """
    __tablename__ = "supplier_variants"
    
    supplier_product_id = Column(UUID(as_uuid=True), ForeignKey("supplier_products.id"), nullable=False)
    variant_id = Column(UUID(as_uuid=True), ForeignKey("product_variants.id"), nullable=False)
    
    cost_price = Column(Numeric(12, 2), nullable=False)
    inventory = Column(Integer, default=0)
    reserved_inventory = Column(Integer, default=0)  # Reserved for orders
    
    status = Column(String(20), default="active")  # active, inactive
    
    raw_payload = Column(JSONB)  # Original Basalam data
    
    # Relationships
    product = relationship("SupplierProduct", back_populates="variants")
    variant = relationship("ProductVariant", back_populates="supplier_variants")
    reservations = relationship("InventoryReservation", back_populates="variant")
    inventory_logs = relationship("InventoryLog", back_populates="variant")
    seller_variants = relationship("SellerVariant", back_populates="supplier_variant")
    
    @property
    def available_inventory(self) -> int:
        """Calculate available inventory"""
        return max(0, self.inventory - self.reserved_inventory)


class ProductMedia(Base, UUIDMixin, TimestampMixin):
    """
    Product images and files
    
    Stored in object storage (S3/MinIO), not in DB
    """
    __tablename__ = "product_media"
    
    product_id = Column(UUID(as_uuid=True), ForeignKey("supplier_products.id"), nullable=False)
    
    media_type = Column(String(20), nullable=False)  # image, video, file
    url = Column(String(1000), nullable=False)
    storage_provider = Column(String(50))  # s3, minio, basalam
    storage_key = Column(String(500))  # Path in storage
    
    hash = Column(String(64))  # For deduplication
    size_bytes = Column(Integer)
    mime_type = Column(String(100))
    
    sort_order = Column(Integer, default=0)
    status = Column(String(20), default="pending")  # pending, processed, failed, rejected
    
    width = Column(Integer)
    height = Column(Integer)
    
    # Relationships
    product = relationship("SupplierProduct", back_populates="images")


# ============================================
# SELLER SIDE
# ============================================

class SellerListing(Base, UUIDMixin, TimestampMixin):
    """
    Seller's copy/listing of a supplier product
    
    Seller adds supplier product to their store with margin
    """
    __tablename__ = "seller_listings"
    
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    supplier_product_id = Column(UUID(as_uuid=True), ForeignKey("supplier_products.id"), nullable=False)
    
    margin_percent = Column(Numeric(5, 2), nullable=False)
    
    # Custom overrides
    custom_title = Column(String(500))
    custom_description = Column(Text)
    custom_images = Column(JSONB, default=list)  # Seller's own images
    
    sync_enabled = Column(Boolean, default=True)  # Auto-sync price/inventory
    sync_price = Column(Boolean, default=True)
    sync_inventory = Column(Boolean, default=True)
    
    status = Column(String(20), default="active")  # active, disabled
    
    # Statistics
    view_count = Column(Integer, default=0)
    order_count = Column(Integer, default=0)
    
    # Relationships
    shop = relationship("Shop", back_populates="seller_listings")
    supplier_product = relationship("SupplierProduct", back_populates="seller_listings")
    variants = relationship("SellerVariant", back_populates="listing", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_seller_listings_shop', 'shop_id'),
        Index('idx_seller_listings_supplier', 'supplier_product_id'),
    )


class SellerVariant(Base, UUIDMixin, TimestampMixin):
    """
    Seller's variant with calculated price
    
    Price = supplier_cost * (1 + margin)
    """
    __tablename__ = "seller_variants"
    
    listing_id = Column(UUID(as_uuid=True), ForeignKey("seller_listings.id"), nullable=False)
    supplier_variant_id = Column(UUID(as_uuid=True), ForeignKey("supplier_variants.id"), nullable=False)
    
    # Calculated price (cached)
    price = Column(Numeric(12, 2), nullable=False)
    inventory_cache = Column(Integer)  # Cached from supplier
    
    # Override settings
    custom_price = Column(Numeric(12, 2))  # Seller's custom price (overrides calculation)
    is_enabled = Column(Boolean, default=True)
    
    # Relationships
    listing = relationship("SellerListing", back_populates="variants")
    supplier_variant = relationship("SupplierVariant", back_populates="seller_variants")
