## Why

Build a **Dropshipping/Marketplace Sync Platform** that connects Basalam marketplace suppliers with sellers/dropshippers. The platform handles product synchronization, inventory management, order processing, and payment escrow. This addresses the need for a reliable bridge between Basalam vendors and external sellers, ensuring real-time sync of prices, inventory, and order status while protecting both parties through escrow payments.

## What Changes

This is a **greenfield project** creating a comprehensive dropshipping platform with:

- **Supplier Management**: Connect Basalam shops via OAuth, manual product upload, or CSV/Sheet import
- **Product Sync Engine**: Real-time synchronization of products, variants, images, prices, and inventory from Basalam
- **Seller Store Management**: Allow sellers to browse catalog, select products, set margins, and override product details
- **Inventory System**: Source-of-truth inventory management with reservation, reconciliation, and race-condition handling
- **Order Lifecycle**: Complete order flow from creation through payment, shipping, delivery confirmation, and dispute resolution
- **Payment Escrow**: Seller → Platform → Supplier payment flow with hold/release mechanism
- **Shipping Integration**: Support multiple shipping types with tracking and delivery confirmation
- **Multi-Platform Ready Architecture**: Strategy pattern for supporting Basalam, Shopify, WooCommerce, and manual connections
- **Forbidden Product Detection**: Validate products against Basalam policies and notify suppliers
- **Admin Panel**: Operational tools for fraud detection, disputes, refunds, and manual overrides
- **Observability**: Comprehensive logging, monitoring, and webhook reliability

## Capabilities

### New Capabilities
- `supplier-connection`: Manage supplier connections to Basalam with OAuth, manual upload, and CSV import
- `product-sync`: Synchronize products, variants, images, prices, and inventory with idempotent webhook handling
- `inventory-management`: Source-of-truth inventory with reservation, reconciliation, and race-condition protection
- `pricing-engine`: Calculate prices through supplier price + margin chain with snapshot at order time
- `seller-catalog`: Allow sellers to browse, filter, select products and manage their store catalog
- `order-lifecycle`: Complete order state machine from creation to delivery confirmation
- `payment-escrow`: Hold-and-release payment flow protecting both seller and supplier
- `shipping-integration`: Handle multiple shipping types with tracking and delivery confirmation logic
- `notification-system`: Multi-channel notifications (SMS, in-app, webhook) for key events
- `forbidden-product-detection`: Validate products against Basalam policies and flag prohibited items
- `admin-operations`: Fraud detection, dispute resolution, refund processing, and manual overrides
- `webhook-reliability`: Idempotent webhook processing with retry logic and dead-letter queue

### Modified Capabilities
- (none - greenfield project)

## Impact

- **New Systems**: 12+ new backend services (FastAPI-based)
- **Database**: 40-50 tables covering users, suppliers, products, inventory, orders, payments, shipments
- **External Integrations**: Basalam API (products, orders, shipping, wallet, webhooks)
- **Infrastructure**: Kafka for event-driven architecture, Redis for caching, PostgreSQL for data
- **Frontend**: Seller Dashboard and Supplier Dashboard (React/Next.js)
- **Monitoring**: Prometheus, Grafana, Sentry, ELK stack for logs
