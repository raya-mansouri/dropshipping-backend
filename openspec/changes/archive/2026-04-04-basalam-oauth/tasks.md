## 1. Configuration & URLs

- [x] 1.1 Fix the value of  `basalam_auth_url`, `basalam_api_url`, `basalam_webhook_url` settings to `src/core/config.py` with defaults `https://auth.basalam.com`, `https://openapi.basalam.com/v1`, `https://webhook.basalam.com/v1`
- [x] 1.2 Update `BasalamClient.__init__` in `src/integrations/basalam/client.py` to use `settings.basalam_api_url` as `BASE_URL` instead of hardcoded `https://api.basalam.com/api/v1`

## 2. Database — SyncState Model & Migration

- [x] 2.1 Create `SyncState` SQLAlchemy model in `src/domains/shops/models.py` with fields: `id` (UUID PK), `integration_id` (UUID FK → shop_integrations), `entity_type` (str), `status` (str), `sync_mode` (str), `last_sync_timestamp` (datetime), `total_synced` (int), `created_count` (int), `updated_count` (int), `failed_count` (int), `last_error` (str), unique constraint on `(integration_id, entity_type)`
- [x] 2.2 Create Alembic migration for `SyncState` table with unique constraint on `(integration_id, entity_type)`
- [x] 2.3 Add `SyncState` relationship to `ShopIntegration` model (`sync_states`)
- [x] 2.4 Create `SyncStateRepository` in `src/domains/shops/repository/sync_state.py` extending `BaseRepository` with `get_by_integration_and_type(integration_id, entity_type)` and `get_or_create(integration_id, entity_type)` methods

## 3. OAuth 2.0 — Authorization URL Generation

- [x] 3.1 Add `exchange_authorization_code(code, redirect_uri)` method to `BasalamClient` that POSTs to `settings.basalam_auth_url + "/oauth/token"` with `grant_type=authorization_code`, `client_id`, `client_secret`, `redirect_uri`, `code`
- [x] 3.2 Add `refresh_access_token_with_code(refresh_token)` method to `BasalamClient` that POSTs to `settings.basalam_auth_url + "/oauth/token"` with `grant_type=refresh_token`
- [x] 3.3 Add `get_current_user(access_token)` method to `BasalamClient` that GETs `settings.basalam_api_url + "/users/me"` and returns `{id, vendor: {id, title}}`
- [x] 3.4 Fix `IntegrationService.start_oauth()` to generate real authorization URL at `https://basalam.com/accounts/sso?client_id={}&scope=vendor.product.read+vendor.parcel.read+vendor.shipping.read&redirect_uri={}&state={}&response_type=code`, store state in Redis with 10-min TTL, return `{authorize_url, state, integration_id}`
- [x] 3.5 Fix `IntegrationService.handle_oauth_callback()` to: verify state from Redis → call `exchange_authorization_code(code)` → call `get_current_user(access_token)` → extract `vendor.id` → encrypt credentials with Fernet → store in `ShopIntegration.credentials_encrypted` and `external_shop_id=vendor_id` → mark integration as `"connected"`

## 4. OAuth — Token Refresh & Encryption

- [x] 4.1 Fix `BasalamClient.refresh_access_token()` to use `settings.basalam_auth_url + "/oauth/token"` instead of `self.BASE_URL + "/oauth/token"`, and to update `self._http_client` headers with new token
- [x] 4.2 Add Redis distributed lock (`oauth:refresh:{integration_id}`, 30s TTL) around token refresh in `IntegrationService` to prevent concurrent refresh race conditions
- [x] 4.3 Fix `BasalamClient.get_access_token()` to use `settings.basalam_auth_url + "/oauth/token"` instead of `self.BASE_URL + "/oauth/token"`
- [x] 4.4 Verify `credentials_encrypted` field stores Fernet-encrypted JSON blob containing `{access_token, refresh_token, vendor_id}` using existing `webhook_secret_encryption_key`

## 5. Product Sync — API Endpoint & Pagination

- [x] 5.1 Fix `ProductSyncService._fetch_products_page()` to call `GET /vendors/{vendor_id}/products` (using `external_shop_id` from integration) with `page` and `per_page` params instead of cursor-based params
- [x] 5.2 Replace cursor-based pagination loop in `_fetch_and_process_products()` with page-based: `for page in range(start_page, total_pages+1)` using `total_page` from API response
- [x] 5.3 Add delta sync support: pass `updated_at_min` param to `_fetch_products_page()` when `SyncState.last_sync_timestamp` exists and `full_sync=False`
- [x] 5.4 Wire `ProductSyncService` to use new `SyncStateRepository` for `get_or_create_sync_state()` and state updates instead of referencing non-existent model

## 6. Product Sync — Mappers

- [x] 6.1 Fix `basalam_product_to_internal()` in `src/integrations/basalam/mappers/product.py` to handle real Basalam product shape: `id` (not `product_id`), `photo{original, id}` (not `images[]`), `status{value}` (numeric, 2976=active), `inventory` (top-level), `is_wholesale`
- [x] 6.2 Fix `basalam_variant_to_internal()` to handle real Basalam variant shape if variants exist in product response
- [x] 6.3 Update `_map_basalam_product()` in `ProductSyncService` to match the corrected mapper output, handling `photo` object for media creation and `status.value` for status mapping

## 7. Webhooks — Registration & Subscription

- [x] 7.1 Fix `BasalamConnectorAdapter.register_webhook()` to POST to `settings.basalam_webhook_url + "/webhooks"` with numeric `event_ids: [8, 5, 7]` (not string names), `request_method: "POST"`, `register_me: true`
- [x] 7.2 Add `subscribe_user_to_webhook(webhook_id, access_token)` method to `BasalamClient` that POSTs to `settings.basalam_webhook_url + "/webhooks/{webhook_id}/subscribe"` with vendor's Bearer token
- [x] 7.3 Update `IntegrationService.connect_shop()` webhook registration flow to: (1) create webhook with numeric event_ids, (2) subscribe vendor with their token, (3) store webhook_id on integration
- [x] 7.4 Fix `BasalamConnectorAdapter.unregister_webhook()` to DELETE to `settings.basalam_webhook_url + "/webhooks/{webhook_id}"` with vendor's Bearer token
- [x] 7.5 Fix `_register_webhook_with_platform()` in `IntegrationService` to use numeric event_ids and 2-step subscribe flow with correct webhook base URL

## 8. Webhooks — Product Processor

- [x] 8.1 Fix `ProductWebhookProcessor.process()` in `src/integrations/webhooks/processors/product.py` to check for `event_id == 8` (numeric) instead of string `"product.created"/"product.updated"`
- [x] 8.2 Fix import in `ProductWebhookProcessor` from `src.domains.suppliers.models` to `src.domains.products.models`
- [x] 8.3 Replace raw `session.commit()` in `ProductWebhookProcessor` with UnitOfWork pattern (use `UnitOfWork(session)` context manager)
- [x] 8.4 Update `_create_product()` and `_update_product()` in `ProductWebhookProcessor` to handle real Basalam webhook payload shape with proper field mapping (photo{}, status{}, inventory)
- [x] 8.5 Fix `BasalamConnectorAdapter.verify_webhook_signature()` — handle `sha256=` prefix from `X-Basalam-Signature` header

## 9. Connector & Adapter Fixes

- [x] 9.1 Fix `BasalamConnectorAdapter.oauth_config` property: update `authorize_url` to `https://basalam.com/accounts/sso`, `token_url` to `settings.basalam_auth_url + "/oauth/token"`, scopes to `["vendor.product.read", "vendor.parcel.read", "vendor.shipping.read"]`
- [x] 9.2 Fix `BasalamConnectorAdapter._get_client()` base URL to use `settings.basalam_api_url` instead of hardcoded `https://api.basalam.com`
- [x] 9.3 Fix `BasalamConnector` in `src/integrations/shop/connectors/basalam_connector.py` to pass `vendor_id` (from `external_shop_id`) to product fetch calls
- [x] 9.4 Fix `BasalamClient.list_products()` to accept `vendor_id` parameter and call `/vendors/{vendor_id}/products` instead of `/products`
- [x] 9.5 Fix `BasalamClient.register_webhook()` and `delete_webhook()` to use `settings.basalam_webhook_url` instead of `self.BASE_URL`

