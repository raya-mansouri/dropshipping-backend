## Why

The existing Basalam integration code is scaffolded with hardcoded or incorrect URLs, a non-functional OAuth flow (stores auth_code without exchanging it for tokens), product sync calling non-existent endpoints, and webhook registration using string event names instead of numeric IDs. Shop owners cannot currently connect their real Basalam shops, The platform needs a working end-to-end integration: shop owner clicks "Connect", authorizes via Basalam OAuth 2.0, products sync to local DB, and webhook-driven product change tracking keeps everything up to date.

## What Changes

- Fix all API base URLs: auth server → `auth.basalam.com`, API → `openapi.basalam.com/v1`, webhooks → `webhook.basalam.com/v1`
- Implement proper OAuth 2.0 Authorization Code flow: generate real authorization URL, exchange code for tokens at `auth.basalam.com/oauth/token`, fetch `vendor_id` from `/users/me`, store encrypted tokens in `ShopIntegration`
- Fix product sync endpoint to `/vendors/{vendor_id}/products` with page-based pagination (not cursor-based)
- Fix webhook registration to use `webhook.basalam.com/v1/webhooks` with numeric `event_ids` [8, 5, 7] and 2-step subscribe flow
- Fix `ProductWebhookProcessor` to handle real Basalam webhook payload format (numeric event types, correct data shape)
- Create missing `SyncState` model and migration
- Fix `ProductSyncService._fetch_products_page()` to use correct endpoint and pagination
- Fix `BasalamConnectorAdapter` OAuth config URLs and scopes (`vendor.product.read` not `vendor.products.read`)

## Capabilities

### New Capabilities
- `basalam-oauth`: OAuth 2.0 Authorization Code flow for connecting Basalam vendor shops — includes generating authorization URL, exchanging code for tokens, fetching vendor info, storing encrypted credentials, refreshing tokens
- `basalam-product-sync`: Fetching and persisting vendor products from Basalam API — includes paginated product fetching, product/variant mapping, bulk upsert, delta sync, and the missing SyncState model
- `basalam-webhooks`: Registering Basalam webhooks with numeric event IDs, subscribing users to webhooks, receiving and processing product/order/inventory change events with correct payload parsing

### Modified Capabilities

## Impact

- **`src/integrations/basalam/client.py`**: Fix BASE_URL, add `exchange_authorization_code()`, add `get_current_user()`, fix `get_access_token()` and `refresh_access_token()` to use correct auth URL
- **`src/integrations/basalam/product_sync.py`**: Fix `_fetch_products_page()` endpoint and pagination format
- **`src/integrations/basalam/mappers/product.py`**: Update mapper to handle real Basalam product shape (`photo{}`, `status{}`, `inventory`)
- **`src/integrations/shop/adapters/basalam.py`**: Fix OAuth config URLs, scopes, and webhook registration
- **`src/integrations/shop/connectors/basalam_connector.py`**: Update `connect()` for real OAuth flow
- **`src/integrations/webhooks/processors/product.py`**: Handle numeric event_id 8, fix import path, use UnitOfWork
- **`src/domains/shops/service/integration_service.py`**: Fix `handle_oauth_callback()` to actually exchange tokens, fix `start_oauth()` to return real auth URL, fix webhook registration with numeric event_ids
- **`src/domains/shops/models.py`**: Add `vendor_id` field to `ShopIntegration`, add `SyncState` model
- **`src/core/config.py`**: Add `basalam_auth_url`, `basalam_api_url`, `basalam_webhook_url` settings
- **Database**: New migration for `SyncState` table, `vendor_id` column on `shop_integrations`
- **API surface**: `POST /shops/{id}/oauth/start` and `POST /shops/{id}/oauth/callback` endpoints behavior changes
