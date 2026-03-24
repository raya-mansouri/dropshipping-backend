# Implementation Tasks - Basalam Dropshipping Platform

**IMPORTANT**: All tables use UUID as PRIMARY KEY (not BIGINT). All IDs must be UUID.

---

## 1. Project Setup & Infrastructure

- [x] 1.1 Initialize FastAPI project with pyproject.toml (Poetry/PEP 621)
- [x] 1.2 Add dependencies: fastapi, sqlalchemy, asyncpg, alembic, celery, redis, aiokafka, pydantic, sentry-sdk
- [x] 1.3 Create .env.example with all environment variables
- [x] 1.4 Configure Alembic for database migrations
- [x] 1.5 Set up docker-compose.yml (PostgreSQL, Redis, Kafka, MinIO)
- [x] 1.6 Configure logging with structlog + Sentry
- [x] 1.7 Create Makefile with common commands

**Libraries**:
```toml
fastapi = "^0.110.0"
sqlalchemy = "^2.0.25"
asyncpg = "^0.29.0"
alembic = "^1.13.0"
celery = "^5.3.0"
redis = "^5.0.0"
aiokafka = "^0.10.0"
pydantic = "^2.6.0"
pydantic-settings = "^2.1.0"
sentry-sdk = "^1.40.0"
```

---

## 2. Database Schema (50+ Tables)

### Core Tables
- [x] 2.1 Create platforms table
- [x] 2.2 Create accounts table
- [x] 2.3 Create shops table (shop_role: supplier OR seller only)
- [x] 2.4 Create shop_integrations table with encrypted credentials
- [x] 2.5 Add UNIQUE constraint: (platform_id, external_shop_id)

### Product Tables
- [x] 2.6 Create categories table (with franchise_percent)
- [x] 2.7 Create supplier_products table (has_variants, status: active/archived/forbidden)
- [x] 2.8 Create product_variants table (attributes JSONB)
- [x] 2.9 Create supplier_variants table (cost_price, inventory)
- [x] 2.10 Create indexes on supplier_products(external_product_id)

### Seller Tables
- [x] 2.11 Create seller_listings table (margin_percent, sync_enabled)
- [x] 2.12 Create seller_variants table (price, inventory_cache)
- [x] 2.13 Create media_files table (storage_provider, hash)

### Order Tables
- [x] 2.14 Create orders table (status state machine)
- [x] 2.15 Create order_items table (supplier_price, seller_price, profit)
- [x] 2.16 Create order indexes (seller_shop_id, status)

### Shipping Tables
- [x] 2.17 Create shipping_methods table
- [x] 2.18 Create supplier_shipping_profiles table
- [x] 2.19 Create shipments table (tracking_code, carrier)

### Payment Tables
- [x] 2.20 Create payments table (escrow status)
- [x] 2.21 Create refunds table
- [x] 2.22 Create supplier_payouts table

### Inventory Tables
- [x] 2.23 Create inventory_reservations table (expires_at for timeout)
- [x] 2.24 Create inventory_logs table (source: webhook/manual/order/reconciliation)

### Webhook Tables
- [x] 2.25 Create webhook_events table (idempotency: UNIQUE(platform_id, external_event_id))
- [x] 2.26 Create processed_events table (event_id PRIMARY KEY)
- [x] 2.27 Create sync_jobs table
- [x] 2.28 Create integration_logs table

### System Tables
- [x] 2.29 Create product_validation_logs table
- [x] 2.30 Create notifications table (channel: sms/in_app/webhook)
- [x] 2.31 Create system_logs table
- [x] 2.32 Create audit_logs table
- [x] 2.33 Create fraud_signals table

---

## 3. Core Architecture Patterns

### Repository Pattern
- [x] 3.1 Implement BaseRepository class with CRUD operations
    - [x] 3.1.1 Create base repository with generic CRUD methods (create, get, get_by_id, update, delete, list)
    - [x] 3.1.2 Implement query builder with filters, pagination, ordering
    - [x] 3.1.3 Add soft delete support with deleted_at timestamp
    - [x] 3.1.4 Add audit trail integration (created_by, updated_by)
- [x] 3.2 Implement UnitOfWork for transaction management
    - [x] 3.2.1 Create UnitOfWork context manager class
    - [x] 3.2.2 Implement commit/rollback with proper error handling
    - [x] 3.2.3 Add integration with repository layer
- [x] 3.3 Create repositories for each domain

### Domain Events
- [x] 3.4 Create DomainEvent base class
    - [x] 3.4.1 Define EventMetadata (event_id, occurred_at, correlation_id)
    - [x] 3.4.2 Create specific event data classes (InventoryEvent, OrderEvent, etc.)
    - [x] 3.4.3 Implement event serialization/deserialization
- [x] 3.5 Implement EventPublisher for Kafka
    - [x] 3.5.1 Create EventPublisher with topic routing
    - [x] 3.5.2 Implement async publishing with error handling
    - [x] 3.5.3 Add event persistence for replay capability
- [x] 3.6 Create specific events: InventoryReserved, OrderCreated, PriceUpdated
    - [ ] 3.6.1 Implement InventoryReservedEvent with variant_id, quantity, order_id
    - [ ] 3.6.2 Implement OrderCreatedEvent with order_id, items, totals
    - [ ] 3.6.3 Implement PriceUpdatedEvent with variant_id, old_price, new_price

### Webhook Idempotency
- [x] 3.7 Implement two-layer dedup (Redis + Database)
    - [ ] 3.7.1 Create Redis-based fast path check (7-day TTL)
    - [ ] 3.7.2 Implement database persistent check (processed_events table)
    - [x] 3.7.3 Add cache warming on startup
- [x] 3.8 Create WebhookProcessor with signature verification
    - [ ] 3.8.1 Implement HMAC-SHA256 signature validation
    - [x] 3.8.2 Add timestamp validation (reject >5 min old)
    - [ ] 3.8.3 Create payload parsing and validation
- [x] 3.9 Implement retry schedule: 1m, 5m, 15m, 1h, 6h (5 attempts)
    - [ ] 3.9.1 Create retry queue with exponential backoff
    - [ ] 3.9.2 Implement dead letter queue (DLQ) for failed events
    - [ ] 3.9.3 Add retry status tracking and monitoring

---

## 4. Basalam Integration

### Client Wrapper
- [x] 4.1 Create BasalamClient wrapper around official SDK
    - [ ] 4.1.1 Initialize client with credentials from shop_integrations
    - [ ] 4.1.2 Implement request/response logging
    - [x] 4.1.3 Add connection pooling configuration
- [x] 4.2 Implement error handling for Basalam API errors
    - [ ] 4.2.1 Create custom exception hierarchy (BasalamAPIError, RateLimitError, AuthError)
    - [ ] 4.2.2 Parse error responses and map to exceptions
    - [ ] 4.2.3 Implement error recovery strategies
- [x] 4.3 Add retry logic with exponential backoff
    - [ ] 4.3.1 Implement retry decorator with configurable attempts
    - [x] 4.3.2 Add jitter to prevent thundering herd
    - [ ] 4.3.3 Track retry metrics
- [x] 4.4 Implement rate limiting (token bucket in Redis)
    - [ ] 4.4.1 Create TokenBucketRateLimiter class
    - [x] 4.4.2 Implement per-endpoint rate limits
    - [ ] 4.4.3 Add rate limit headers parsing (X-RateLimit-*)

### Shop Connector
- [x] 4.5 Create abstract ShopConnector interface
    - [x] 4.5.1 Define connector contract (connect, disconnect, fetch_products, etc.)
    - [x] 4.5.2 Implement base connector with common functionality
    - [x] 4.5.3 Add connector factory for dynamic instantiation
- [x] 4.6 Implement BasalamConnector with all methods
    - [ ] 4.6.1 Implement get_products() with pagination
    - [ ] 4.6.2 Implement get_product_variants()
    - [ ] 4.6.3 Implement get_inventory(), update_inventory()
    - [ ] 4.6.4 Implement create_order(), get_order_status()
    - [ ] 4.6.5 Implement get_shipping_methods()
- [x] 4.7 Create data mappers (Basalam payload → Internal model)
    - [ ] 4.7.1 Create ProductMapper (BasalamProduct → SupplierProduct)
    - [ ] 4.7.2 Create VariantMapper (BasalamVariant → SupplierVariant)
    - [ ] 4.7.3 Create OrderMapper (Internal → BasalamOrder)
    - [ ] 4.7.4 Handle category mapping with franchise_percent

### Product Sync
- [x] 4.8 Implement full product import with pagination
    - [ ] 4.8.1 Create paginated fetch with cursor-based pagination
    - [ ] 4.8.2 Implement delta sync using last_modified timestamps
    - [ ] 4.8.3 Add bulk insert with conflict resolution
- [x] 4.9 Implement variant sync
    - [ ] 4.9.1 Sync variant attributes (size, color, etc.)
    - [ ] 4.9.2 Sync variant-specific pricing
    - [ ] 4.9.3 Handle variant-level inventory
- [x] 4.10 Implement image download → upload to S3 → CDN pipeline
    - [ ] 4.10.1 Download images from Basalam CDN
    - [ ] 4.10.2 Upload to MinIO/S3 with optimization
    - [ ] 4.10.3 Generate CDN URLs and store
    - [ ] 4.10.4 Handle duplicate image detection via hash
- [x] 4.11 Handle forbidden product errors from Basalam API
    - [ ] 4.11.1 Parse forbidden product responses
    - [ ] 4.11.2 Update product status to forbidden
    - [ ] 4.11.3 Notify sellers with affected products

---

## 5. Inventory System

### Reservation
- [x] 5.1 Implement atomic inventory locking (SELECT FOR UPDATE)
    - [ ] 5.1.1 Create database-level locking with FOR UPDATE
    - [ ] 5.1.2 Implement proper transaction isolation
    - [x] 5.1.3 Add deadlock detection and retry logic
- [x] 5.2 Create reserve_inventory function with transaction
    - [ ] 5.2.1 Validate sufficient inventory before reservation
    - [ ] 5.2.2 Create inventory_reservations record with expires_at
    - [ ] 5.2.3 Update supplier_variants inventory atomically
    - [x] 5.2.4 Handle partial reservation scenarios
- [x] 5.3 Implement release_inventory on cancellation
    - [ ] 5.3.1 Delete/expire inventory_reservations record
    - [ ] 5.3.2 Restore inventory to supplier_variants
    - [ ] 5.3.3 Create inventory_logs for audit trail
- [x] 5.4 Create reservation expiration job (check expires_at < NOW())
    - [ ] 5.4.1 Implement Celery periodic task (every 1 min)
    - [ ] 5.4.2 Query expired reservations with batch processing
    - [ ] 5.4.3 Release inventory and update order status to cancelled

### Reconciliation
- [x] 5.5 Create inventory reconciliation job (every 15 min) - exists in inventory_tasks.py
    - [x] 5.5.1 Implement Celery beat schedule
    - [x] 5.5.2 Add distributed locking to prevent concurrent runs
    - [x] 5.5.3 Create reconciliation report generation
- [x] 5.6 Compare supplier inventory vs platform - exists in sync_service.py
    - [x] 5.6.1 Fetch current inventory from Basalam API
    - [x] 5.6.2 Compare with supplier_variants inventory
    - [x] 5.6.3 Calculate discrepancies and variance
- [x] 5.7 Log corrections and notify sellers - exists in inventory_tasks.py
    - [x] 5.7.1 Apply inventory corrections with approval
    - [x] 5.7.2 Create inventory_logs with source=reconciliation
    - [x] 5.7.3 Send notifications to affected sellers

---

## 6. Order Lifecycle

### State Machine
- [x] 6.1 Define order states: pending → confirmed → paid → processing → shipped → delivered → completed
    - [x] 6.1.1 Create OrderStatus enum with all states (exists in orders/models.py)
    - [x] 6.1.2 Define valid state transitions in configuration
    - [x] 6.1.3 Add state transition timestamps (confirmed_at, paid_at, etc.)
- [x] 6.2 Define failure states: cancelled, disputed, refunded
    - [x] 6.2.1 Add cancellation reasons enum (exists in orders/models.py)
    - [x] 6.2.2 Implement dispute workflow
    - [x] 6.2.3 Handle partial refunds
- [x] 6.3 Implement state transition validation
    - [x] 6.3.1 Create StateMachine service class
    - [x] 6.3.2 Validate transitions before applying
    - [x] 6.3.3 Emit domain events on state change (exists in order_service.py)

### Order Creation
- [x] 6.4 Validate inventory availability
    - [x] 6.4.1 Check inventory for each variant in cart (exists in order_service.py)
    - [x] 6.4.2 Handle inventory check failures gracefully
    - [x] 6.4.3 Add real-time inventory validation endpoint
- [x] 6.5 Reserve inventory atomically
    - [x] 6.5.1 Call reserve_inventory for each variant (exists in order_service.py)
    - [x] 6.5.2 Handle partial reservation failures
    - [x] 6.5.3 Rollback all reservations on failure
- [x] 6.6 Snapshot prices (supplier_price_at_order, seller_price_at_order)
    - [x] 6.6.1 Capture supplier_price at order time from supplier_variants
    - [x] 6.6.2 Calculate seller_price using current margin (exists in order_service.py and pricing service)
    - [x] 6.6.3 Store price_snapshot JSONB in order_items
    - [x] 6.6.4 Implement price lock duration (e.g., 15 min)
- [x] 6.7 Split orders by supplier (order_supplier_groups)
    - [x] 6.7.1 Group order items by supplier_shop_id (exists in order_service.py)
    - [x] 6.7.2 Create order_supplier_groups table
    - [x] 6.7.3 Track supplier-specific totals and status
    - [x] 6.7.4 Handle partial supplier fulfillment

### Payment Escrow
- [x] 6.8 Implement hold payment after seller pays
    - [x] 6.8.1 Create escrow record on payment success (exists in payment logic)
    - [x] 6.8.2 Hold funds until delivery confirmation
    - [x] 6.8.3 Calculate platform fee from escrow
- [x] 6.9 Create delivery confirmation logic (carrier/customer/auto-72h)
    - [x] 6.9.1 Implement carrier webhook-based confirmation
    - [x] 6.9.2 Add customer confirmation via API (POST /orders/{id}/confirm-delivery) (exists in orders/service)
    - [x] 6.9.3 Implement auto-confirmation after 72 hours (normal) / 7 days (high-value)
    - [x] 6.9.4 Add 72-hour dispute window logic
    - [x] 6.9.5 Handle high-value order threshold (e.g., >$100 = 7 days)
- [x] 6.10 Release payment to supplier after confirmation
    - [x] 6.10.1 Calculate supplier payout amount
    - [x] 6.10.2 Deduct platform commission (exists in payment logic)
    - [x] 6.10.3 Create supplier_payouts record
    - [x] 6.10.4 Process payout via Basalam

---

## 7. Pricing Engine

- [x] 7.1 Implement price calculation: supplier_price + margin = seller_price
    - [x] 7.1.1 Create PriceCalculator service class (exists in pricing/service.py)
    - [x] 7.1.2 Calculate seller_price = supplier_price * (1 + margin_percent / 100)
    - [x] 7.1.3 Add rounding logic (round to nearest 100 for IRR)
    - [x] 7.1.4 Implement price tiers for bulk quantities
    - [x] 7.1.5 Add shipping cost to price when applicable
- [x] 7.2 Create price snapshot at order time
    - [x] 7.2.1 Capture supplier_price_at_order from supplier_variants.cost_price
    - [x] 7.2.2 Capture seller_price_at_order with margin applied (exists in pricing/service.py)
    - [x] 7.2.3 Store snapshot in order_items table
    - [x] 7.2.4 Implement price lock for pending orders (15 min)
- [x] 7.3 Implement price history tracking
    - [x] 7.3.1 Create price_history table (exists - PriceHistory model)
    - [x] 7.3.2 Track price changes over time
    - [x] 7.3.3 Query historical prices for analytics
- [x] 7.4 Add category franchise validation (minimum margin per category)
    - [x] 7.4.1 Fetch category franchise_percent from categories table
    - [x] 7.4.2 Validate seller margin >= category minimum (exists in pricing/service.py - FranchiseValidator)
    - [x] 7.4.3 Reject listings that violate franchise rules
    - [x] 7.4.4 Add category detection from Basalam API (categorydetection.basalam.com)

---

## 8. Kafka & Workers

### Topics
- [x] 8.1 Create topics: webhook.received, product.updated, inventory.updated, order.created, payment.updated
    - [x] 8.1.1 Configure Kafka topic: webhook.received (partition by platform_id)
    - [x] 8.1.2 Configure Kafka topic: product.updated (partition by product_id)
    - [x] 8.1.3 Configure Kafka topic: inventory.updated (partition by variant_id)
    - [x] 8.1.4 Configure Kafka topic: order.created (partition by order_id)
    - [x] 8.1.5 Configure Kafka topic: payment.updated (partition by payment_id)
    - [x] 8.1.6 Set up topic retention policies (7 days default)
    - [x] 8.1.7 Configure partition count based on load

### Consumers
- [x] 8.2 Create product_consumer worker
    - [x] 8.2.1 Consume from product.updated topic
    - [x] 8.2.2 Handle product create/update/delete events
    - [x] 8.2.3 Sync to seller_listings
    - [x] 8.2.4 Implement consumer group for scalability
- [x] 8.3 Create inventory_consumer worker
    - [x] 8.3.1 Consume from inventory.updated topic
    - [x] 8.3.2 Update supplier_variants inventory
    - [x] 8.3.3 Trigger low inventory notifications
- [x] 8.4 Create order_consumer worker
    - [x] 8.4.1 Consume from order.created topic
    - [x] 8.4.2 Process order confirmation workflow
    - [x] 8.4.3 Trigger supplier order creation

### Celery Tasks
- [x] 8.5 Create product_sync task (every 30 min) - add to celery_config.py beat_schedule
- [x] 8.6 Create inventory_sync task (every 5 min) - exists in inventory_tasks.py
- [x] 8.7 Create order_sync task (every 2 min)
- [x] 8.8 Create reconciliation tasks (daily) - exists (reconcile_inventory)
- [x] 8.9 Create cleanup_expired_reservations task (every 5 min) - exists in inventory_tasks.py

---

## 9. API Endpoints

### Authentication
- [x] 9.1 POST /auth/register
- [x] 9.2 POST /auth/login
- [x] 9.3 POST /auth/refresh
- [x] 9.4 Implement JWT with access/refresh tokens

### Shops
- [x] 9.5 POST /shops (create shop)
    - [x] 9.5.1 Implement shop creation with role selection (supplier/seller)
- [x] 9.6 POST /shops/{id}/connect (connect to platform)
    - [x] 9.6.1 OAuth flow initiation
    - [x] 9.6.2 Callback handling and token storage
- [x] 9.7 GET /shops/{id}/products
    - [x] 9.7.1 List products with pagination
    - [x] 9.7.2 Apply filters (category, status, price range)

### Products
- [x] 9.8 GET /products (browse catalog with filters)
    - [x] 9.8.1 Full-text search implementation
    - [x] 9.8.2 Filter by category, price, supplier
    - [x] 9.8.3 Sort by price, popularity, newest
- [x] 9.9 POST /products (seller adds to store)
    - [x] 9.9.1 Validate category franchise rules
    - [x] 9.9.2 Set margin percentage
    - [x] 9.9.3 Create seller_listing record
- [x] 9.10 PATCH /products/{id}/override
    - [x] 9.10.1 Override title, description, images
    - [x] 9.10.2 Override pricing (within franchise limits)
    - [x] 9.10.3 Track override history
- [x] 9.11 GET /products/{id}
- [x] 9.12 PUT /products/{id}
- [x] 9.13 DELETE /products/{id}

### Orders
- [x] 9.14 POST /orders (create order)
    - [x] 9.14.1 Validate cart items and availability
    - [x] 9.14.2 Calculate totals with price snapshot
    - [x] 9.14.3 Reserve inventory
- [x] 9.15 GET /orders/{id}
    - [x] 9.15.1 Include order items, supplier groups
- [x] 9.16 PATCH /orders/{id}/cancel
    - [x] 9.16.1 Validate cancellation window
    - [x] 9.16.2 Release inventory reservations
    - [x] 9.16.3 Process refund if paid
- [x] 9.17 GET /orders
    - [x] 9.17.1 List with filters (status, date range)
    - [x] 9.17.2 Pagination support
- [x] 9.18 PATCH /orders/{id}
- [x] 9.19 POST /orders/{id}/confirm-delivery

### Payments
- [x] 9.20 GET /payments/{id}
- [x] 9.21 POST /payments
- [x] 9.22 GET /payments
- [x] 9.23 POST /payments/{id}/refund

### Admin
- [x] 9.24 GET /admin/sync/status
    - [x] 9.24.1 Show last sync timestamps
    - [x] 9.24.2 Display sync job queue status
- [x] 9.25 POST /admin/webhook/retry
    - [x] 9.25.1 Retry failed webhook events
    - [x] 9.25.2 Specify event ID or date range
- [x] 9.26 PATCH /admin/inventory/force
    - [x] 9.26.1 Force update inventory
    - [x] 9.26.2 Require admin authentication
- [x] 9.27 PATCH /admin/order/force-cancel
    - [x] 9.27.1 Override normal cancellation rules
    - [x] 9.27.2 Log admin action for audit
- [x] 9.28 GET /admin/shops
- [x] 9.29 PATCH /admin/shops/{id}
- [x] 9.30 GET /admin/users
- [x] 9.31 PATCH /admin/users/{id}

---

## 10. Notification System

- [x] 10.1 Create NotificationService (exists in notification/manager.py)
- [x] 10.3 Implement SMS notifications (Kavenegar)
- [x] 10.4 Implement in-app notifications
- [x] 10.5 Create notification preferences

---

## 11. Observability

- [x] 11.1 Set up Prometheus metrics (exists in metrics.py)
- [x] 11.2 Create Grafana dashboards
- [x] 11.3 Implement health check endpoint (exists in health.py)
- [x] 11.4 Set up structured logging (exists in logging.py)

---

## 12. Testing

- [x] 12.1 Write unit tests for inventory reservation (exists in test_inventory_reservation.py)
- [x] 12.2 Write integration tests for webhook processing
- [x] 12.3 Write idempotency tests
- [x] 12.4 Write order flow tests
- [x] 12.5 Set up CI/CD pipeline

---

## 13. Implementation Patterns Reference

### Pattern: Inventory Reservation (Atomic Locking)
```python
async def reserve_inventory(variant_id: UUID, quantity: int, order_id: UUID):
    async with session.begin():
        # SELECT FOR UPDATE
        result = await session.execute(
            text("""
                SELECT inventory FROM supplier_variants 
                WHERE id = :variant_id FOR UPDATE
            """),
            {"variant_id": variant_id}
        )
        if result.scalar() < quantity:
            raise InsufficientInventoryError()
        
        await session.execute(
            text("UPDATE supplier_variants SET inventory = inventory - :qty WHERE id = :id"),
            {"qty": quantity, "id": variant_id}
        )
```

### Pattern: Webhook Idempotency
```python
async def process_webhook(platform: str, event_id: str, payload: dict):
    # Layer 1: Redis
    if await redis.exists(f"webhook:{platform}:{event_id}"):
        return "duplicate"
    
    # Layer 2: Database
    if await processed_events.exists(platform, event_id):
        await redis.setex(f"webhook:{platform}:{event_id}", timedelta(days=7), "done")
        return "duplicate"
    
    # Process
    await process_event(payload)
    await processed_events.create(platform, event_id)
```

### Pattern: Price Snapshot
```python
async def create_order_items(order_id: UUID, items: List[OrderItemCreate]):
    for item in items:
        variant = await variant_repo.get(item.variant_id)
        supplier_price = variant.cost_price
        listing = await listing_repo.get_by_variant(item.variant_id)
        seller_price = supplier_price * (1 + listing.margin_percent / 100)
        
        await order_item_repo.create(OrderItem(
            order_id=order_id,
            variant_id=item.variant_id,
            quantity=item.quantity,
            supplier_price_at_order=supplier_price,
            seller_price_at_order=seller_price,
            profit=seller_price - supplier_price
        ))
```
