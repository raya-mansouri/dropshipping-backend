# COMPREHENSIVE IMPLEMENTATION PLAN
## Basalam Dropshipping Platform - Specs vs a.md Analysis

---

# PART 1: SPECS vs a.md COMPARISON

## Current Specs (12 total)

| # | Spec Name | a.md Coverage | Status | Gaps |
|---|-----------|---------------|--------|------|
| 1 | supplier-connection | ✅ Full | Good | - |
| 2 | product-sync | ✅ Full | Good | Missing: revision/moderation handling |
| 3 | inventory-management | ✅ Full | Good | - |
| 4 | pricing-engine | ✅ Full | Good | Missing: category franchise validation |
| 5 | seller-catalog | ✅ Full | Good | - |
| 6 | order-lifecycle | ✅ Full | Good | Missing: delivery confirmation logic detail |
| 7 | payment-escrow | ✅ Full | Good | - |
| 8 | shipping-integration | ✅ Full | Good | Missing: specific Basalam shipping types |
| 9 | notification-system | ✅ Full | Good | - |
| 10 | forbidden-product-detection | ✅ Full | Good | - |
| 11 | admin-operations | ✅ Full | Good | - |
| 12 | webhook-reliability | ✅ Full | Good | - |

## Gaps Identified

### Gap 1: Revision/Moderation from Basalam
**From a.md**: Basalam has revision.basalam.com for product moderation
**Spec Status**: Not explicitly covered
**Action**: Need to add revision handling spec

### Gap 2: Category Detection
**From a.md**: Basalam has categorydetection.basalam.com
**Spec Status**: Only in forbidden-product-detection
**Action**: Need explicit category detection spec

### Gap 3: Delivery Confirmation Logic (Detailed)
**From a.md**: 
- 3 days normal, 7 days high value
- 72-hour dispute window
- Auto-confirm timer
**Spec Status**: Partially covered in shipping-integration
**Action**: Need more detail in order-lifecycle

### Gap 4: Shipping Types
**From a.md**: basalam_post, supplier_shipping, express, pickup
**Spec Status**: Generic shipping covered
**Action**: Need Basalam-specific shipping types

### Gap 5: Category Franchise Rules
**From a.md**: Each category has specific franchise/margin in Basalam
**Spec Status**: Mentioned in pricing-engine
**Action**: Need explicit validation logic

---

# PART 2: COMPREHENSIVE IMPLEMENTATION PLAN

## Phase 1: Foundation (Week 1-2)
**Goal**: Infrastructure and Core Database

### 1.1 Project Setup
- [ ] Initialize FastAPI project
- [ ] Set up PostgreSQL, Redis, Kafka, MinIO
- [ ] Configure Alembic migrations
- [ ] Set up logging + Sentry

### 1.2 Database Schema (50+ tables)
All tables from ERD in REVIEW_AND_IMPLEMENTATION_DETAILS.md
- UUID primary keys
- Proper indexes
- Constraints

**Start with this SPEC**: `supplier-connection` 
**Why**: Need accounts, shops, shop_integrations tables first

---

## Phase 2: Core Domain (Week 3-5)
**Goal**: Basic supplier/seller functionality

### 2.1 Supplier Connection (supplier-connection)
**Dependencies**: None (foundation)
**Priority**: 1st
**Key Requirements**:
- OAuth connection to Basalam
- Manual product upload
- CSV/Sheet import
- Token refresh logic

**Implementation Order**:
1. Create shops tables
2. Implement OAuth flow
3. Create token storage
4. Build manual upload
5. Build CSV import

### 2.2 Product Sync (product-sync)
**Dependencies**: supplier-connection
**Priority**: 2nd
**Key Requirements**:
- Full product import
- Variant sync
- Image sync
- Webhook handling

---

## Phase 3: Inventory & Pricing (Week 6-8)
**Goal**: Core business logic

### 3.1 Inventory Management (inventory-management)
**Dependencies**: product-sync
**Priority**: 3rd
**Key Requirements**:
- Source of truth from supplier
- Atomic reservation
- Reconciliation job
- Race condition handling

**Why Priority 3**: Can't handle orders without inventory

### 3.2 Pricing Engine (pricing-engine)
**Dependencies**: product-sync, inventory-management
**Priority**: 4th
**Key Requirements**:
- Price calculation (cost + margin)
- Price snapshot at order
- Category franchise validation

---

## Phase 4: Orders & Payments (Week 9-12)
**Goal**: Complete order flow

### 4.1 Seller Catalog (seller-catalog)
**Dependencies**: pricing-engine
**Priority**: 5th
**Key Requirements**:
- Browse products
- Add to store
- Override details

### 4.2 Order Lifecycle (order-lifecycle)
**Dependencies**: seller-catalog, inventory-management
**Priority**: 6th
**Key Requirements**:
- Order creation
- State machine
- Multi-supplier splitting
- Delivery confirmation (detailed)

### 4.3 Payment Escrow (payment-escrow)
**Dependencies**: order-lifecycle
**Priority**: 7th
**Key Requirements**:
- Payment collection
- Escrow hold
- Payment release

---

## Phase 5: Support Systems (Week 13-15)
**Goal**: Complete platform

### 5.1 Shipping Integration
**Dependencies**: order-lifecycle
**Priority**: 8th
**Key Requirements**:
- Basalam shipping methods
- Tracking
- Delivery confirmation

### 5.2 Webhook Reliability
**Dependencies**: All sync
**Priority**: 9th (parallel)
**Key Requirements**:
- Idempotency
- Retry logic
- DLQ

### 5.3 Notification System
**Dependencies**: All
**Priority**: 10th
**Key Requirements**:
- Multi-channel
- Event-based

---

## Phase 6: Operations (Week 16-18)
**Goal**: Admin and monitoring

### 6.1 Forbidden Product Detection
**Dependencies**: product-sync
**Priority**: 11th
**Key Requirements**:
- Category validation
- Keyword filtering
- Revision status sync

### 6.2 Admin Operations
**Dependencies**: All
**Priority**: 12th
**Key Requirements**:
- Force operations
- Fraud detection
- Dispute resolution

---

# PART 3: DETAILED FIRST SPEC IMPLEMENTATION

## Start Here: supplier-connection

### Why First?
1. **Foundation**: Creates accounts, shops, integrations tables
2. **No dependencies**: Everything else depends on having shops connected
3. **Quick win**: OAuth flow is straightforward
4. **Enables everything**: Can't sync products without connected shop

### Implementation Steps

#### Step 1: Database Models
```python
# models for supplier-connection

class Platform(Base):
    __tablename__ = "platforms"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    code = Column(String(50), unique=True)  # 'basalam', 'shopify'
    name = Column(String(255))
    type = Column(String(50))  # 'marketplace', 'seller_system'
    created_at = Column(DateTime, default=datetime.utcnow)

class Account(Base):
    __tablename__ = "accounts"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    owner_user_id = Column(UUID, nullable=False)
    account_type = Column(String(20))  # 'supplier', 'seller'
    created_at = Column(DateTime, default=datetime.utcnow)

class Shop(Base):
    __tablename__ = "shops"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    account_id = Column(UUID, ForeignKey("accounts.id"))
    name = Column(String(255))
    shop_role = Column(String(20))  # 'supplier' OR 'seller' ONLY
    status = Column(String(20), default='active')
    created_at = Column(DateTime, default=datetime.utcnow)

class ShopIntegration(Base):
    __tablename__ = "shop_integrations"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    shop_id = Column(UUID, ForeignKey("shops.id"))
    platform_id = Column(UUID, ForeignKey("platforms.id"))
    external_shop_id = Column(String(255))
    connection_type = Column(String(20))  # 'oauth', 'api', 'manual'
    credentials_encrypted = Column(JSONB)  # encrypted tokens
    status = Column(String(20), default='connected')
    created_at = Column(DateTime, default=datetime.utcnow)
```

#### Step 2: API Endpoints
```python
# POST /shops - Create shop
# POST /shops/{id}/connect - Connect to Basalam
# GET /shops/{id}/status - Connection status
# DELETE /shops/{id}/disconnect - Disconnect
```

#### Step 3: OAuth Flow
```
1. Supplier clicks "Connect Basalam"
2. Redirect to Basalam OAuth URL
3. Basalam redirects back with code
4. Exchange code for tokens
5. Store encrypted tokens
6. Fetch shop info
7. Create shop_integrations record
```

#### Step 4: Token Refresh
```python
async def refresh_token(integration: ShopIntegration):
    credentials = decrypt(integration.credentials_encrypted)
    
    response = await http_client.post(
        f"{BASALAM_API_URL}/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": credentials["refresh_token"],
            "client_id": BASALAM_CLIENT_ID,
            "client_secret": BASALAM_CLIENT_SECRET
        }
    )
    
    new_tokens = response.json()
    integration.credentials_encrypted = encrypt(new_tokens)
    await integration.save()
```

---

# PART 4: QUICK START CHECKLIST

## Today - Start Here

### Day 1: Project Setup
- [ ] Initialize FastAPI project
- [ ] Add dependencies to pyproject.toml
- [ ] Create .env.example
- [ ] Set up docker-compose.yml
- [ ] Run PostgreSQL, Redis, Kafka

### Day 2-3: Database
- [ ] Create Alembic config
- [ ] Create initial migration for platforms, accounts, shops, shop_integrations
- [ ] Run migration
- [ ] Verify tables created

### Day 4-5: API Foundation
- [ ] Create FastAPI app
- [ ] Implement /shops endpoints
- [ ] Implement OAuth flow
- [ ] Test connection

### Day 6-7: Integration
- [ ] Create Basalam client wrapper
- [ ] Implement token storage
- [ ] Test full OAuth flow
- [ ] Handle errors

---

# PART 5: ORDER OF SPECS TO IMPLEMENT

| Order | Spec | Week | Priority Reason |
|-------|------|------|-----------------|
| 1 | supplier-connection | 1-2 | Foundation - no dependencies |
| 2 | product-sync | 2-3 | Depends on #1 |
| 3 | inventory-management | 4-5 | Core business logic |
| 4 | pricing-engine | 5-6 | Depends on #2, #3 |
| 5 | seller-catalog | 6-7 | Depends on #4 |
| 6 | order-lifecycle | 8-10 | Depends on #5 |
| 7 | payment-escrow | 10-11 | Depends on #6 |
| 8 | shipping-integration | 11-12 | Depends on #6 |
| 9 | webhook-reliability | 8-12 | Parallel with #6-8 |
| 10 | notification-system | 12-14 | Depends on all |
| 11 | forbidden-product-detection | 14-15 | Depends on #2 |
| 12 | admin-operations | 15-16 | Final polish |

---

## SUMMARY

**START WITH**: `supplier-connection`

**WHY**:
1. Creates foundation (shops, integrations)
2. No other specs depend on it being complete
3. OAuth is straightforward to implement
4. Enables all other features

**COMPLETE BY**: End of Week 2

**NEXT AFTER**: `product-sync` (Week 2-3)
