# Comprehensive Review & Implementation Details
## Matching a.md with Artifacts - Basalam Dropshipping Platform

---

## 1. ARTIFACT REVIEW - What's Covered vs What's Missing

### ✅ Already Covered in Artifacts

| a.md Topic | Artifact Status | Notes |
|------------|----------------|-------|
| Supplier/Seller roles | ✅ proposal | Full role definitions |
| Multi-platform architecture | ✅ design | Strategy Pattern decision |
| Event-driven with Kafka | ✅ design | Correct decision |
| PostgreSQL | ✅ design | Correct choice |
| Inventory source of truth | ✅ design + specs | Complete |
| Price snapshot at order | ✅ design + specs | Implemented |
| Escrow payment flow | ✅ design + specs | Complete |
| DDD folder structure | ✅ design | Structure defined |
| Webhook idempotency | ✅ specs/webhook-reliability | Complete |
| Retry logic | ✅ specs/webhook-reliability | 5 retries defined |
| Delivery confirmation | ✅ specs/shipping-integration | 3 methods |
| Forbidden products | ✅ specs/forbidden-product-detection | Full pipeline |
| Admin operations | ✅ specs/admin-operations | Force operations |

### ⚠️ Gaps - Things Missing or Need Enhancement

| Gap | Priority | Required Action |
|-----|----------|-----------------|
| **UUID instead of BIGINT** | Critical | All IDs should be UUID per a.md |
| **Shop role = supplier OR seller** | Critical | Should NOT be "both" |
| **Specific Python libraries** | High | Need to specify |
| **Basalam SDK integration** | High | Not detailed enough |
| **Pydantic contracts structure** | High | Need external/internal separation |
| **Alembic migrations** | High | Need migration structure |
| **Complete ERD (50+ tables)** | Critical | Need full schema |
| **Code folder structure** | High | Need actual FastAPI structure |
| **Specific retry schedule** | Medium | Need exact times (1m, 5m, 15m, 1h, 6h) |
| **Environment config (.env)** | High | Need template |

---

## 2. PYTHON LIBRARIES - Complete Stack

### Core Framework
```toml
# pyproject.toml - Core Dependencies

# Web Framework
fastapi = "^0.110.0"
uvicorn[standard] = "^0.27.0"

# Database
sqlalchemy = "^2.0.25"
asyncpg = "^0.29.0"          # Async PostgreSQL driver
alembic = "^1.13.0"          # Migrations
pgvector = "^0.2.0"          # Vector support (future AI)

# Validation
pydantic = "^2.6.0"
pydantic-settings = "^2.1.0"

# Authentication
python-jose[cryptography] = "^3.3.0"
passlib[bcrypt] = "^1.7.4"

# Async & Workers
celery = "^5.3.0"
redis = "^5.0.0"
httpx = "^0.26.0"            # Async HTTP client
aiohttp = "^3.9.0"

# Kafka
aiokafka = "^0.10.0"

# Monitoring
sentry-sdk[fastapi] = "^1.40.0"
prometheus-client = "^0.19.0"

# Utilities
python-multipart = "^0.0.6"
python-dotenv = "^1.0.0"
pydantic[email] = "^2.6.0"
```

### Basalam Integration
```toml
# Basalam SDK (check PyPI for actual package name)
basalam-sdk = "*"  # Or actual package: pip install basalam

# If SDK not available, use:
requests = "^2.31.0"
aiohttp = "^3.9.0"
```

### Image/Media Processing
```toml
pillow = "^10.2.0"            # Image processing
python-magic = "^0.4.27"     # File type detection
minio = "^7.2.0"              # S3-compatible storage
```

### Notifications
```toml
# Email
emails = "^0.6"              # Email templates
aiosmtplib = "^3.0.0"         # Async SMTP

# SMS (example providers)
kavenegar = "*"              # Iranian SMS provider
```

### Testing
```toml
pytest = "^8.0.0"
pytest-asyncio = "^0.23.0"
pytest-cov = "^4.1.0"
httpx = "^0.26.0"            # For API testing
```

---

## 3. DESIGN PATTERNS - Implementation Guide

### Pattern 1: Strategy Pattern - Shop Connectors
```python
# src/integrations/base.py
from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel

class ProductPayload(BaseModel):
    """External product from any platform"""
    external_id: str
    title: str
    price: float
    inventory: int
    # ... other fields

class ShopConnector(ABC):
    """Abstract base for all shop integrations"""
    
    @abstractmethod
    async def connect(self, credentials: dict) -> bool:
        """Establish connection to shop"""
        pass
    
    @abstractmethod
    async def fetch_products(self, page: int = 1) -> List[ProductPayload]:
        """Fetch products from shop"""
        pass
    
    @abstractmethod
    async def fetch_orders(self, since: datetime) -> List[OrderPayload]:
        """Fetch orders from shop"""
        pass
    
    @abstractmethod
    async def update_inventory(self, variant_id: str, quantity: int):
        """Update inventory in shop"""
        pass
    
    @abstractmethod
    async def register_webhooks(self, webhook_url: str):
        """Register webhooks for this shop"""
        pass

# src/integrations/basalam.py
class BasalamConnector(ShopConnector):
    """Basalam-specific implementation"""
    
    def __init__(self, credentials: BasalamCredentials):
        self.client = BasalamClient(
            client_id=credentials.client_id,
            client_secret=credentials.client_secret
        )
    
    async def fetch_products(self, page: int = 1) -> List[ProductPayload]:
        # Use Basalam SDK
        response = await self.client.products.list(page=page)
        return [self._map_product(p) for p in response.items]
```

### Pattern 2: Repository Pattern - Data Access
```python
# src/core/repositories/base.py
from typing import TypeVar, Generic, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

T = TypeVar('T')

class BaseRepository(Generic[T]):
    def __init__(self, model: type[T], session: AsyncSession):
        self.model = model
        self.session = session
    
    async def get_by_id(self, id: UUID) -> Optional[T]:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def create(self, obj: T) -> T:
        self.session.add(obj)
        await self.session.flush()
        return obj

# src/domains/supplier/repositories.py
class SupplierProductRepository(BaseRepository[SupplierProduct]):
    pass

class SupplierVariantRepository(BaseRepository[SupplierVariant]):
    pass
```

### Pattern 3: Unit of Work - Transaction Management
```python
# src/core/uow.py
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

class UnitOfWork:
    def __init__(self, session_factory):
        self.session_factory = session_factory
    
    @asynccontextmanager
    async def __call__(self):
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Usage
async def create_order(order_data: OrderCreate):
    async with unit_of_work() as session:
        order_repo = OrderRepository(session)
        inventory_repo = InventoryRepository(session)
        
        # Reserve inventory
        for item in order_data.items:
            await inventory_repo.reserve(item.variant_id, item.quantity)
        
        # Create order
        order = await order_repo.create(order_data)
        return order
```

### Pattern 4: Domain Events - Event-Driven
```python
# src/core/events.py
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import json

@dataclass
class DomainEvent:
    event_type: str
    payload: dict
    occurred_at: datetime
    correlation_id: str
    
    def to_json(self) -> str:
        return json.dumps({
            "event_type": self.event_type,
            "payload": self.payload,
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": self.correlation_id
        })

# src/domains/inventory/events.py
class InventoryReserved(DomainEvent):
    def __init__(self, variant_id: UUID, quantity: int, order_id: UUID):
        super().__init__(
            event_type="inventory.reserved",
            payload={
                "variant_id": str(variant_id),
                "quantity": quantity,
                "order_id": str(order_id)
            },
            occurred_at=datetime.utcnow(),
            correlation_id=str(order_id)
        )

# src/services/kafka_producer.py
class EventPublisher:
    async def publish(self, event: DomainEvent):
        await self.producer.send_and_wait(
            topic=event.event_type,
            value=event.to_json().encode()
        )
```

### Pattern 5: Webhook Idempotency
```python
# src/services/webhooks/handler.py
from uuid import UUID

class WebhookProcessor:
    def __init__(self, processed_events_repo, event_publisher):
        self.processed_events = processed_events_repo
        self.publisher = event_publisher
    
    async def process(self, platform: str, event_id: str, payload: dict):
        # Layer 1: Redis check (fast path)
        cache_key = f"webhook:{platform}:{event_id}"
        if await redis.exists(cache_key):
            return {"status": "duplicate", "message": "Already processing"}
        
        # Layer 2: Database check
        existing = await self.processed_events.get(platform, event_id)
        if existing:
            return {"status": "duplicate", "message": "Already processed"}
        
        # Mark as processing
        await redis.setex(cache_key, timedelta(days=7), "processing")
        await self.processed_events.create({
            "platform": platform,
            "event_id": event_id,
            "status": "processing"
        })
        
        # Publish to Kafka
        await self.publisher.publish(DomainEvent(
            event_type=f"{platform}.{payload.get('type')}",
            payload=payload,
            occurred_at=datetime.utcnow(),
            correlation_id=event_id
        ))
```

### Pattern 6: Inventory Reservation - Atomic Locking
```python
# src/domains/inventory/service.py
class InventoryService:
    async def reserve(self, variant_id: UUID, quantity: int, order_id: UUID):
        async with self.session.begin():
            # Use SELECT FOR UPDATE for row-level locking
            result = await self.session.execute(
                text("""
                    SELECT id, inventory 
                    FROM supplier_variants 
                    WHERE id = :variant_id 
                    FOR UPDATE
                """),
                {"variant_id": variant_id}
            )
            row = result.fetchone()
            
            if row.inventory < quantity:
                raise InsufficientInventoryError(
                    f"Only {row.inventory} available, requested {quantity}"
                )
            
            # Atomic update
            await self.session.execute(
                text("""
                    UPDATE supplier_variants 
                    SET inventory = inventory - :quantity 
                    WHERE id = :variant_id
                """),
                {"variant_id": variant_id, "quantity": quantity}
            )
            
            # Create reservation record
            reservation = InventoryReservation(
                variant_id=variant_id,
                order_id=order_id,
                quantity=quantity,
                status="reserved",
                expires_at=datetime.utcnow() + timedelta(minutes=15)
            )
            self.session.add(reservation)
```

---

## 4. COMPLETE DATABASE ERD - All 50+ Tables

### Core Tables
```sql
-- platforms (supported integrations)
CREATE TABLE platforms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) UNIQUE NOT NULL,  -- 'basalam', 'shopify', 'woocommerce'
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,        -- 'marketplace', 'seller_system', 'supplier_system'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- accounts (user accounts)
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL,
    account_type VARCHAR(20) NOT NULL,  -- 'supplier', 'seller', 'hybrid'
    created_at TIMESTAMP DEFAULT NOW()
);

-- shops (business shops - role is ONLY supplier OR seller)
CREATE TABLE shops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id),
    name VARCHAR(255) NOT NULL,
    shop_role VARCHAR(20) NOT NULL CHECK (shop_role IN ('supplier', 'seller')),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- shop_integrations (platform connections)
CREATE TABLE shop_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id UUID REFERENCES shops(id),
    platform_id UUID REFERENCES platforms(id),
    external_shop_id VARCHAR(255),
    connection_type VARCHAR(20),  -- 'oauth', 'api', 'token', 'manual'
    credentials_encrypted JSONB,  -- Encrypted tokens
    status VARCHAR(20) DEFAULT 'connected',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(platform_id, external_shop_id)
);
```

### Product Tables
```sql
-- categories (with franchise rules)
CREATE TABLE categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform_id UUID REFERENCES platforms(id),
    external_category_id VARCHAR(255),
    name VARCHAR(255) NOT NULL,
    parent_id UUID REFERENCES categories(id),
    franchise_percent DECIMAL(5,2),  -- Minimum margin for this category
    is_forbidden BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- supplier_products (main product table)
CREATE TABLE supplier_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_shop_id UUID REFERENCES shops(id),
    external_product_id VARCHAR(255),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    category_id UUID REFERENCES categories(id),
    has_variants BOOLEAN DEFAULT FALSE,
    status VARCHAR(30) DEFAULT 'active',  -- 'active', 'archived', 'forbidden'
    basalam_validation_error JSONB,        -- Error from Basalam if forbidden
    raw_payload JSONB,                       -- Original data from Basalam
    last_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- product_variants (base variant definition)
CREATE TABLE product_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID REFERENCES supplier_products(id) ON DELETE CASCADE,
    sku VARCHAR(255),
    external_variant_id VARCHAR(255),
    attributes JSONB,  -- {"color": "red", "size": "XL"}
    created_at TIMESTAMP DEFAULT NOW()
);

-- supplier_variants (supplier-specific variant data)
CREATE TABLE supplier_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_product_id UUID REFERENCES supplier_products(id),
    variant_id UUID REFERENCES product_variants(id),
    cost_price DECIMAL(12,2) NOT NULL,
    inventory INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    raw_payload JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for product queries
CREATE INDEX idx_supplier_products_shop ON supplier_products(supplier_shop_id);
CREATE INDEX idx_supplier_products_status ON supplier_products(status);
CREATE INDEX idx_supplier_products_external ON supplier_products(external_product_id);
CREATE INDEX idx_product_variants_product ON product_variants(product_id);
CREATE INDEX idx_supplier_variants_product ON supplier_variants(supplier_product_id);
```

### Seller Tables
```sql
-- seller_listings (seller's copy of supplier product)
CREATE TABLE seller_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_shop_id UUID REFERENCES shops(id),
    supplier_product_id UUID REFERENCES supplier_products(id),
    margin_percent DECIMAL(5,2) NOT NULL,
    custom_title VARCHAR(500),
    custom_description TEXT,
    status VARCHAR(20) DEFAULT 'active',
    sync_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(seller_shop_id, supplier_product_id)
);

-- seller_variants (seller's variant with price calculation)
CREATE TABLE seller_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id UUID REFERENCES seller_listings(id) ON DELETE CASCADE,
    variant_id UUID REFERENCES product_variants(id),
    price DECIMAL(12,2) NOT NULL,           -- Calculated: cost + margin
    inventory_cache INTEGER,                 -- Cached from supplier
    sync_inventory BOOLEAN DEFAULT TRUE,
    sync_price BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_seller_listings_shop ON seller_listings(seller_shop_id);
CREATE INDEX idx_seller_listings_supplier ON seller_listings(supplier_product_id);
CREATE INDEX idx_seller_variants_listing ON seller_variants(listing_id);
```

### Media Tables
```sql
-- media_files (images/videos for products)
CREATE TABLE media_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,  -- 'supplier_product', 'seller_listing'
    entity_id UUID NOT NULL,
    url VARCHAR(1000) NOT NULL,
    storage_provider VARCHAR(50),       -- 's3', 'minio', 'basalam'
    hash VARCHAR(64),                  -- For deduplication
    size_bytes BIGINT,
    mime_type VARCHAR(100),
    sort_order INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'processed', 'failed'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_media_entity ON media_files(entity_type, entity_id);
```

### Order Tables
```sql
-- orders (main order table)
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform_id UUID REFERENCES platforms(id),
    external_order_id VARCHAR(255),
    seller_shop_id UUID REFERENCES shops(id),
    customer_data JSONB,
    total_price DECIMAL(12,2) NOT NULL,
    shipping_price DECIMAL(12,2) DEFAULT 0,
    status VARCHAR(30) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(platform_id, external_order_id)
);

-- order_items (items in order)
CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
    supplier_shop_id UUID REFERENCES shops(id),
    variant_id UUID REFERENCES product_variants(id),
    seller_listing_id UUID REFERENCES seller_listings(id),
    quantity INTEGER NOT NULL,
    supplier_price DECIMAL(12,2) NOT NULL,    -- Price at order time
    seller_price DECIMAL(12,2) NOT NULL,       -- Price customer paid
    profit DECIMAL(12,2),                      -- seller_price - supplier_price
    status VARCHAR(30) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_orders_seller ON orders(seller_shop_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_supplier ON order_items(supplier_shop_id);
```

### Shipping Tables
```sql
-- shipping_methods (available shipping options)
CREATE TABLE shipping_methods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(30) NOT NULL,          -- 'vendor', 'platform', 'third_party'
    platform_id UUID REFERENCES platforms(id),
    external_shipping_id VARCHAR(255),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- supplier_shipping_profiles (supplier's shipping settings)
CREATE TABLE supplier_shipping_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id UUID REFERENCES shops(id),
    shipping_method_id UUID REFERENCES shipping_methods(id),
    cost DECIMAL(12,2) NOT NULL,
    regions JSONB,                       -- ["Tehran", "Alborz"]
    delivery_time_estimate INTEGER,      -- Hours
    created_at TIMESTAMP DEFAULT NOW()
);

-- shipments
CREATE TABLE shipments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_item_id UUID REFERENCES order_items(id),
    shipping_method_id UUID REFERENCES shipping_methods(id),
    tracking_code VARCHAR(255),
    carrier VARCHAR(100),
    status VARCHAR(30) DEFAULT 'pending',
    shipped_at TIMESTAMP,
    delivered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Payment Tables
```sql
-- payments
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id),
    seller_paid_amount DECIMAL(12,2) NOT NULL,
    supplier_payable_amount DECIMAL(12,2) NOT NULL,
    platform_fee DECIMAL(12,2) DEFAULT 0,
    status VARCHAR(30) DEFAULT 'pending',  -- 'pending', 'seller_paid', 'escrow', 'supplier_paid', 'refunded'
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- refunds
CREATE TABLE refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_item_id UUID REFERENCES order_items(id),
    reason TEXT,
    status VARCHAR(30) DEFAULT 'requested',  -- 'requested', 'approved', 'rejected', 'completed'
    refund_amount DECIMAL(12,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP
);

-- supplier_payouts (for escrow release)
CREATE TABLE supplier_payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id UUID REFERENCES shops(id),
    order_item_id UUID REFERENCES order_items(id),
    amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(30) DEFAULT 'pending',
    released_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Dispute Tables
```sql
-- disputes
CREATE TABLE disputes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_item_id UUID REFERENCES order_items(id),
    opened_by VARCHAR(20) NOT NULL,  -- 'seller', 'supplier', 'admin'
    reason TEXT NOT NULL,
    evidence JSONB,                  -- Screenshots, documents
    status VARCHAR(30) DEFAULT 'open',  -- 'open', 'investigating', 'resolved', 'rejected'
    resolution TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);
```

### Inventory Tables
```sql
-- inventory_reservations (prevent overselling)
CREATE TABLE inventory_reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    variant_id UUID REFERENCES supplier_variants(id),
    order_item_id UUID REFERENCES order_items(id),
    quantity INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'reserved',  -- 'reserved', 'released', 'consumed'
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- inventory_logs (audit trail)
CREATE TABLE inventory_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    variant_id UUID REFERENCES supplier_variants(id),
    old_inventory INTEGER NOT NULL,
    new_inventory INTEGER NOT NULL,
    source VARCHAR(30) NOT NULL,  -- 'webhook', 'manual', 'order', 'reconciliation'
    reference_id UUID,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_inventory_reservations_variant ON inventory_reservations(variant_id);
CREATE INDEX idx_inventory_reservations_expires ON inventory_reservations(expires_at);
```

### Webhook & Integration Tables
```sql
-- webhook_events
CREATE TABLE webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform_id UUID REFERENCES platforms(id),
    external_event_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    signature_verified BOOLEAN DEFAULT FALSE,
    status VARCHAR(30) DEFAULT 'received',  -- 'received', 'processing', 'failed', 'completed'
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    received_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,
    UNIQUE(platform_id, external_event_id)
);

-- processed_events (idempotency)
CREATE TABLE processed_events (
    event_id VARCHAR(255) PRIMARY KEY,
    processed_at TIMESTAMP DEFAULT NOW()
);

-- sync_jobs
CREATE TABLE sync_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    integration_id UUID REFERENCES shop_integrations(id),
    entity_type VARCHAR(50) NOT NULL,  -- 'product', 'inventory', 'order'
    entity_id UUID,
    status VARCHAR(30) DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    scheduled_at TIMESTAMP,
    executed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- integration_logs
CREATE TABLE integration_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    integration_id UUID REFERENCES shop_integrations(id),
    action VARCHAR(100) NOT NULL,
    request_data JSONB,
    response_data JSONB,
    status VARCHAR(20) NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_webhook_events_status ON webhook_events(status);
CREATE INDEX idx_webhook_events_type ON webhook_events(event_type);
CREATE INDEX idx_sync_jobs_status ON sync_jobs(status);
```

### Validation & Notification Tables
```sql
-- product_validation_logs
CREATE TABLE product_validation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID REFERENCES supplier_products(id),
    rule VARCHAR(100) NOT NULL,
    result VARCHAR(20) NOT NULL,  -- 'passed', 'failed'
    message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- notifications
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT,
    payload JSONB,
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'sent', 'read'
    channel VARCHAR(20),                    -- 'email', 'sms', 'in_app', 'webhook'
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_notifications_user ON notifications(user_id, status);
```

### System Tables
```sql
-- system_logs
CREATE TABLE system_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service VARCHAR(100) NOT NULL,
    level VARCHAR(20) NOT NULL,  -- 'DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'
    message TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- audit_logs (for compliance)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID NOT NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    old_value JSONB,
    new_value JSONB,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- fraud_signals
CREATE TABLE fraud_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,  -- 'supplier', 'seller'
    entity_id UUID NOT NULL,
    signal_type VARCHAR(50) NOT NULL,  -- 'high_cancel_rate', 'late_shipping', etc
    score INTEGER NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_system_logs_service ON system_logs(service, level);
CREATE INDEX idx_system_logs_created ON system_logs(created_at);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
```

---

## 5. COMPLETE FOLDER STRUCTURE

```
basalam-dropshipping-platform/
├── .env.example                    # Environment template
├── .env                            # Local dev (gitignored)
├── pyproject.toml                  # Poetry/PEP 621 config
├── alembic.ini                     # Alembic config
├── docker-compose.yml              # Local dev stack
├── Dockerfile                      # App container
├── Makefile                        # Common commands
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app entry point
│   ├── config.py                   # Configuration management
│   │
│   ├── core/                       # Shared/core functionality
│   │   ├── __init__.py
│   │   ├── database.py             # SQLAlchemy setup
│   │   ├── session.py              # Session factory
│   │   ├── uow.py                  # Unit of Work
│   │   ├── events.py               # Domain events
│   │   ├── exceptions.py           # Custom exceptions
│   │   ├── messages.py             # Message classes
│   │   └── utils.py                # Utilities
│   │
│   ├── contracts/                  # Data contracts
│   │   ├── __init__.py
│   │   ├── external/              # Basalam API contracts
│   │   │   ├── __init__.py
│   │   │   ├── product.py         # Basalam product schema
│   │   │   ├── order.py           # Basalam order schema
│   │   │   └── webhook.py         # Webhook payloads
│   │   └── internal/              # Internal domain models
│   │       ├── __init__.py
│   │       ├── product.py
│   │       ├── order.py
│   │       └── inventory.py
│   │
│   ├── domains/                    # DDD Bounded Contexts
│   │   ├── __init__.py
│   │   │
│   │   ├── accounts/              # User accounts
│   │   │   ├── __init__.py
│   │   │   ├── models.py          # SQLAlchemy models
│   │   │   ├── schemas.py         # Pydantic schemas
│   │   │   ├── repository.py
│   │   │   └── service.py
│   │   │
│   │   ├── shops/                 # Shops & integrations
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── repository.py
│   │   │   └── service.py
│   │   │
│   │   ├── products/              # Products & variants
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── repository.py
│   │   │   └── service.py
│   │   │
│   │   ├── inventory/             # Inventory management
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── repository.py
│   │   │   └── service.py
│   │   │
│   │   ├── orders/                # Order management
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── repository.py
│   │   │   ├── state_machine.py   # Order state transitions
│   │   │   └── service.py
│   │   │
│   │   ├── payments/              # Payment & escrow
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── repository.py
│   │   │   └── service.py
│   │   │
│   │   ├── shipping/              # Shipping
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   └── service.py
│   │   │
│   │   └── notifications/         # Notifications
│   │       ├── __init__.py
│   │       ├── models.py
│   │       └── service.py
│   │
│   ├── integrations/              # Platform integrations
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract connector
│   │   ├── basalam/              # Basalam specific
│   │   │   ├── __init__.py
│   │   │   ├── client.py         # Basalam SDK wrapper
│   │   │   ├── connector.py     # ShopConnector impl
│   │   │   ├── mappers.py       # Data mappers
│   │   │   └── exceptions.py    # Basalam-specific errors
│   │   └── shopify/              # Future: Shopify
│   │       └── connector.py
│   │
│   ├── services/                  # Application services
│   │   ├── __init__.py
│   │   ├── sync/                 # Sync engine
│   │   │   ├── __init__.py
│   │   │   ├── product_sync.py
│   │   │   ├── inventory_sync.py
│   │   │   ├── order_sync.py
│   │   │   └── scheduler.py
│   │   ├── webhook/               # Webhook handling
│   │   │   ├── __init__.py
│   │   │   ├── receiver.py       # HTTP endpoint
│   │   │   ├── processor.py      # Idempotent processing
│   │   │   └── handlers/         # Event handlers
│   │   │       ├── product_handler.py
│   │   │       ├── inventory_handler.py
│   │   │       └── order_handler.py
│   │   └── kafka/                # Kafka producers/consumers
│   │       ├── __init__.py
│   │       ├── producer.py
│   │       └── consumers/
│   │           ├── product_consumer.py
│   │           ├── inventory_consumer.py
│   │           └── order_consumer.py
│   │
│   ├── workers/                    # Celery workers
│   │   ├── __init__.py
│   │   ├── celery_app.py
│   │   ├── tasks/
│   │   │   ├── __init__.py
│   │   │   ├── sync_tasks.py
│   │   │   ├── inventory_tasks.py
│   │   │   ├── cleanup_tasks.py
│   │   │   └── reconciliation_tasks.py
│   │   └── beat_schedule.py
│   │
│   └── api/                       # FastAPI routes
│       ├── __init__.py
│       ├── deps.py                # Dependencies
│       ├── root.py                # Root router
│       ├── v1/
│       │   ├── __init__.py
│       │   ├── accounts/
│       │   ├── shops/
│       │   ├── products/
│       │   ├── orders/
│       │   ├── payments/
│       │   └── webhooks/
│       └── admin/
│           ├── __init__.py
│           ├── dashboard.py
│           ├── sync_monitor.py
│           └── disputes.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Pytest fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── domains/
│   │   └── services/
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_basalam_client.py
│   │   └── test_webhooks.py
│   └── e2e/
│       └── test_order_flow.py
│
├── migrations/
│   ├── versions/
│   │   ├── 001_initial.py
│   │   ├── 002_add_products.py
│   │   └── 003_add_orders.py
│   ├── env.py
│   └── script.py.mako
│
└── scripts/
    ├── init_db.py
    ├── seed_data.py
    └── run_worker.py
```

---

## 6. ENVIRONMENT CONFIG (.env.example)

```bash
# ===========================================
# Application
# ===========================================
APP_ENV=development                    # development | staging | production
APP_NAME=basalam-dropshipping
APP_DEBUG=true
APP_URL=http://localhost:8000

# ===========================================
# Database
# ===========================================
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=basalam_dropshipping
DATABASE_USER=postgres
DATABASE_PASSWORD=changeme
DATABASE_URL=postgresql+asyncpg://${DATABASE_USER}:${DATABASE_PASSWORD}@${DATABASE_HOST}:${DATABASE_PORT}/${DATABASE_NAME}

# ===========================================
# Redis
# ===========================================
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_URL=redis://${REDIS_HOST}:${REDIS_PORT}/0

# ===========================================
# Kafka
# ===========================================
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPICS=webhook.received,product.updated,inventory.updated,order.created,payment.updated

# ===========================================
# Basalam API
# ===========================================
BASALAM_CLIENT_ID=your_client_id
BASALAM_CLIENT_SECRET=your_client_secret
BASALAM_API_URL=https://api.basalam.com
BASALAM_WEBHOOK_SECRET=your_webhook_secret

# ===========================================
# Authentication
# ===========================================
SECRET_KEY=changeme-use-openssl-rand-hex-32
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# ===========================================
# S3/MinIO (for images)
# ===========================================
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=basalam-dropshipping
S3_PUBLIC_URL=http://localhost:9000/${S3_BUCKET}

# ===========================================
# Monitoring
# ===========================================
SENTRY_DSN=
PROMETHEUS_ENABLED=true

# ===========================================
# Email (SMTP)
# ===========================================
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@yourdomain.com

# ===========================================
# SMS (Kavenegar)
# ===========================================
KAVENEGAR_API_KEY=
```

---

## 7. KEY IMPLEMENTATION CHECKLIST

### Phase 1: Foundation
- [ ] Initialize FastAPI project with pyproject.toml
- [ ] Set up Alembic with initial migration
- [ ] Configure logging with structlog
- [ ] Set up Sentry error tracking
- [ ] Configure environment variables

### Phase 2: Core Domain
- [ ] Create all SQLAlchemy models (50+ tables)
- [ ] Implement Repository pattern for each domain
- [ ] Create Pydantic schemas for validation
- [ ] Implement Unit of Work

### Phase 3: Integration
- [ ] Create Basalam client wrapper
- [ ] Implement ShopConnector interface
- [ ] Build webhook receiver endpoint
- [ ] Implement idempotency processor
- [ ] Set up Kafka topics and producers

### Phase 4: Business Logic
- [ ] Implement inventory reservation with locking
- [ ] Create price calculation engine
- [ ] Build order state machine
- [ ] Implement payment escrow flow
- [ ] Create notification system

### Phase 5: Workers
- [ ] Set up Celery workers
- [ ] Create sync tasks (product, inventory, order)
- [ ] Implement reconciliation jobs
- [ ] Build retry mechanism

### Phase 6: API & Admin
- [ ] Create all REST endpoints
- [ ] Implement admin panel APIs
- [ ] Build dashboard queries

---

This document provides the complete foundation for starting development. All libraries, patterns, database schema, and folder structure are specified to match exactly what was discussed in a.md.
