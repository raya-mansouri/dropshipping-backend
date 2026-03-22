## Context

This is a **greenfield project** for a Dropshipping/Marketplace Sync Platform that bridges Basalam marketplace with external sellers/dropshippers. 

**Current State:**
- No existing system - building from scratch
- Basalam provides API for products, orders, shipping, wallet, and webhooks
- Need to support multiple shop types (Basalam first, then Shopify, WooCommerce)

**Constraints:**
- Supplier inventory is the "source of truth" - sellers cannot override inventory
- Must handle race conditions in inventory (multi-seller ordering same item)
- Payment model: Seller → Platform → Supplier with escrow
- Must be event-driven for reliability and scalability
- Sync reliability is the primary goal - cache should not affect sync

**Stakeholders:**
- Platform operators
- Suppliers (Taminson-konandeh) - Basalam vendors
- Sellers (Dropshippers) - external sellers

## Goals / Non-Goals

**Goals:**
1. Build reliable real-time product sync from Basalam (prices, inventory, images)
2. Handle order lifecycle from seller store → supplier shipping → delivery confirmation
3. Implement escrow payment flow protecting both seller and supplier
4. Support multiple shop types with Strategy Pattern
5. Handle all critical edge cases (race conditions, webhooks, price changes)
6. Provide operational tools (admin, fraud detection, disputes)

**Non-Goals:**
1. Building a customer-facing storefront (sellers have their own)
2. Payment gateway implementation (use existing gateway)
3. Customer support ticketing system (basic dispute flow only)
4. Multi-currency support (IRR only initially)
5. Mobile apps (web-based dashboards only)

## Decisions

### 1. Event-Driven Architecture with Kafka
**Decision:** Use Kafka as the central event bus for all async operations.

**Rationale:**
- Basalam webhooks need reliable processing
- Multiple workers need to react to inventory/price changes
- Order processing requires sequential state changes
- Enables replayability for reconciliation

**Alternatives Considered:**
- RabbitMQ: Good but less suited for high-volume event streaming
- Direct database polling: Not reliable, creates load

### 2. Database: PostgreSQL with Row-Level Security
**Decision:** Use PostgreSQL as the primary database.

**Rationale:**
- Strong ACID compliance for financial transactions
- JSON support for flexible product attributes
- Row-level security for multi-tenant data isolation
- Rich ecosystem for monitoring (pg_stat_statements)

**Alternatives Considered:**
- MySQL: Weaker JSON support, less flexible
- NoSQL (MongoDB): Not suitable for transactional orders

### 3. Strategy Pattern for Shop Connections
**Decision:** Abstract shop connections using Strategy Pattern.

**Rationale:**
- Need to support Basalam, Shopify, WooCommerce, Manual
- Each platform has different APIs, auth flows, webhook formats
- Easy to add new platforms without changing core logic

**Implementation:**
```
ShopConnector (Interface)
├── BasalamConnector
├── ShopifyConnector
├── WooCommerceConnector
└── ManualConnector
```

### 4. Inventory: Source-of-Truth with Reservation
**Decision:** Supplier inventory is source of truth; platform maintains reservation.

**Rationale:**
- Prevents overselling when multiple sellers have same product
- Allows graceful handling of concurrent orders
- Enables reconciliation jobs to fix mismatches

**Inventory Model:**
```
Available = Supplier Inventory - Reserved - Sold
Reserved = Pending orders awaiting payment confirmation
Sold = Confirmed orders
```

### 5. Price Calculation: Snapshot at Order Time
**Decision:** Calculate final price at order creation and snapshot.

**Rationale:**
- Protects seller from price changes during checkout
- Protects supplier from margin manipulation
- Creates clear audit trail

**Price Chain:**
```
Supplier Price + Supplier Discount + Seller Margin = Seller Price
```

### 6. Payment: Escrow with Delivery-Confirmed Release
**Decision:** Hold payment until delivery confirmed or timeout.

**Rationale:**
- Prevents supplier getting paid without shipping
- Prevents seller losing money if never delivered
- Reduces disputes

**Flow:**
```
Order Created → Inventory Reserved → Seller Pays → Platform Holds → 
Supplier Ships → Delivered → 72h No Dispute → Release to Supplier
```

### 7. Webhook Reliability: Idempotency + Retry
**Decision:** Every webhook must have idempotency key with exponential backoff retry.

**Rationale:**
- Basalam webhooks can be duplicated
- Network failures can drop webhooks
- Need DLQ for failed processing

**Implementation:**
- `processed_events` table with unique event_id
- Retry: 1m, 5m, 15m, 1h, 6h (5 attempts)
- Dead letter queue after max retries

### 8. Image Handling: Object Storage + CDN
**Decision:** Store images in S3-compatible storage, serve via CDN.

**Rationale:**
- Database BLOB kills performance
- Need image optimization (resize, compress)
- Basalam images may change

**Pipeline:**
```
Basalam Image → Download → Upload to Storage → 
Image Worker (resize, compress) → CDN → Cache
```

### 9. Caching Strategy: Read-Optimization Only
**Decision:** Never cache inventory, price, order status.

**Rationale:**
- Sync is the primary goal - stale data is dangerous
- Cache categories, product descriptions, supplier info only

**Cache Layers:**
- L1: Application memory
- L2: Redis
- L3: Database

### 10. DDD Folder Structure
**Decision:** Organize code by Domain/Bounded Context.

**Structure:**
```
src/
├── domains/
│   ├── supplier/
│   ├── catalog/
│   ├── seller/
│   ├── order/
│   ├── inventory/
│   └── payment/
├── services/
│   ├── api/
│   ├── workers/
│   └── webhooks/
└── integrations/
    └── basalam/
```

## Risks / Trade-offs

### Risk: Race Condition in Inventory
**Mitigation:** 
- Database-level locking (SELECT FOR UPDATE)
- Optimistic concurrency with version field
- Reconciliation job every 15 minutes

### Risk: Webhook Duplication
**Mitigation:**
- Idempotency keys in `processed_events` table
- Check before processing any webhook

### Risk: Price Change During Checkout
**Mitigation:**
- Snapshot price at order creation
- Show price lock warning to buyer
- 15-minute checkout timeout

### Risk: Supplier Deletes Product
**Mitigation:**
- When webhook received, immediately disable seller products
- Notify sellers via notification
- Keep order history intact

### Risk: API Rate Limiting
**Mitigation:**
- Token bucket in Redis
- Worker throttling
- Backoff: 1s, 2s, 4s, 8s on 429

### Risk: Payment Race Condition
**Mitigation:**
- Database transactions for payment processing
- Idempotency for payment webhooks
- Reconciliation job for wallet sync

### Risk: Image Sync Performance
**Mitigation:**
- Async image processing via Kafka
- CDN caching with invalidation
- Multiple image sizes generated in background

### Risk: Order Splitting Complexity
**Mitigation:**
- Separate `order_supplier_groups` table
- Each group has independent status
- Platform coordinates but doesn't control supplier

### Trade-off: Complexity vs. Reliability
The event-driven, DDD architecture adds complexity but is necessary for:
- Reliability in sync operations
- Scalability for multiple sellers/suppliers
- Maintainability for future platform types

### Trade-off: Real-time vs. Consistency
- Near-real-time sync (webhooks) vs. eventual consistency
- Accept small delay for reliability
- Background jobs for reconciliation

## Migration Plan

Since this is a greenfield project:
1. **Phase 1**: Core infrastructure (DB, Kafka, Redis)
2. **Phase 2**: Supplier connection + product sync
3. **Phase 3**: Seller catalog + pricing
4. **Phase 4**: Order lifecycle + payments
5. **Phase 5**: Admin operations + observability

**Rollback Strategy:**
- Database migrations use additive changes only
- Feature flags for new features
- Blue-green deployment for infrastructure

## Open Questions

1. **Seller Store Platform**: What platform(s) will sellers use? (Custom, Shopify, WooCommerce?)
2. **Payment Gateway**: Which gateway for seller → platform payments?
3. **Supplier Onboarding**: Manual approval or automatic?
4. **Fraud Rules**: What thresholds trigger fraud alerts?
5. **Category Margins**: Where to store franchise/margin rules per category?
