## Context

The dropshipping platform already has scaffolded Basalam integration code across 4 layers: `BasalamClient` (HTTP), `BasalamConnector`/`BasalamConnectorAdapter` (ports/adapters), `IntegrationService`/`SyncService` (domain services), and `ProductSyncService` (sync engine). The architecture is solid — DDD domains, ports/adapters, UnitOfWork, webhook processors with idempotency. However, none of the Basalam API calls match the real endpoints. The code was written against assumed/guessed URLs. We need to fix the API contract layer without changing the architectural patterns.

**Current state**: 3 hosts exist in Basalam's API surface:
- `auth.basalam.com` — OAuth token exchange
- `openapi.basalam.com/v1` — REST API (users, products, orders)
- `webhook.basalam.com/v1` — Webhook CRUD + subscription

The code currently uses a single `api.basalam.com/api/v1` for everything, which is wrong.

## Goals / Non-Goals

**Goals:**
- Fix OAuth 2.0 Authorization Code flow end-to-end (auth URL → code exchange → vendor_id → encrypted token storage)
- Fix product sync to use correct `/vendors/{vendor_id}/products` endpoint with page-based pagination
- Fix webhook registration to use `webhook.basalam.com` with numeric event IDs and 2-step subscribe flow
- Create the missing `SyncState` model + migration
- Make `ProductWebhookProcessor` handle real Basalam webhook payloads (event_id 8)
- All changes fit into existing architectural patterns — no new layers or abstractions

**Non-Goals:**
- Shopify or WooCommerce connector implementation (stubs remain stubs)
- Frontend UI for OAuth flow (backend provides endpoints, frontend consumes them)
- Celery/Kafka async task execution wiring (sync is triggered synchronously or via API call)
- Order sync implementation (only product sync for now, order webhooks are registered but not processed)
- Full Basalam SDK integration (`basalam-sdk` pip package) — we call the REST API directly

## Decisions

### 1. Three separate base URLs in config

**Decision**: Add `basalam_auth_url`, `basalam_api_url`, `basalam_webhook_url` as separate settings instead of a single `BASE_URL`.

**Rationale**: Basalam uses 3 different hosts. A single base URL with path overrides is fragile and confusing. Separate URLs make it clear which service is being called.

**Alternative considered**: Single base URL with per-method overrides — rejected because it hides the multi-host reality.

```
Settings additions:
  basalam_auth_url: str = "https://auth.basalam.com"
  basalam_api_url: str = "https://openapi.basalam.com/v1"
  basalam_webhook_url: str = "https://webhook.basalam.com/v1"
```

### 2. OAuth state stored in Redis (not DB)

**Decision**: Store the CSRF `state` parameter in Redis with 10-minute TTL, not in PostgreSQL.

**Rationale**: OAuth state is ephemeral (lives ~30 seconds in practice). Redis TTL handles cleanup automatically. No need for a DB round-trip or cleanup job.

**Alternative considered**: Store in DB with cleanup cron — over-engineered for a temporary value.

### 3. Encrypt OAuth tokens using existing Fernet infrastructure

**Decision**: Use the same `webhook_secret_encryption_key` Fernet key already in settings to encrypt the entire credentials JSON blob.

**Rationale**: Encryption infrastructure already exists in `webhook_secret_service.py`. Reusing it avoids introducing a second encryption key. The `credentials_encrypted` JSONB column stores the Fernet-encrypted string.

### 4. `vendor_id` stored as `external_shop_id` on `ShopIntegration`

**Decision**: Store Basalam's `vendor.id` in the existing `ShopIntegration.external_shop_id` column rather than adding a new column.

**Rationale**: `external_shop_id` already exists and is designed for exactly this purpose — the external platform's shop/vendor identifier. No schema change needed.

### 5. Page-based pagination (not cursor-based)

**Decision**: Replace the cursor-based pagination in `ProductSyncService` with page-based pagination using `page`/`per_page` parameters.

**Rationale**: Basalam API returns `{total_page, page, per_page, total_count}`. Cursor-based doesn't exist. The `_fetch_and_process_products` loop changes from cursor tracking to page incrementing.

**Implementation**: Change the loop from `while has_more` with cursor to `for page in range(1, total_pages+1)`.

### 6. SyncState model in shops domain

**Decision**: Create `SyncState` as a new SQLAlchemy model in `src/domains/shops/models.py` with a 1:1 relationship to `ShopIntegration`.

**Rationale**: The model is referenced by `ProductSyncService` but doesn't exist. It tracks sync cursor, timestamps, counts, and status per entity type per integration.

```
SyncState:
  id: UUID (PK)
  integration_id: UUID (FK → shop_integrations)
  entity_type: str ("product" | "inventory" | "order")
  status: str ("idle" | "syncing" | "error")
  sync_mode: str ("full" | "delta")
  last_sync_timestamp: datetime
  total_synced: int
  created_count: int
  updated_count: int
  failed_count: int
  last_error: str
  Unique constraint: (integration_id, entity_type)
```

### 7. 2-step webhook subscription flow

**Decision**: After creating a webhook via `POST /v1/webhooks`, subscribe the vendor via `POST /v1/webhooks/{id}/subscribe` using the vendor's own access token.

**Rationale**: Basalam webhook docs require this 2-step flow. Step 1 creates the webhook (can use platform or user token). Step 2 subscribes the specific user so their events flow to the webhook URL. Using the vendor's token for step 2 ensures events are filtered to their shop.

### 8. Webhook event processing uses numeric event_id

**Decision**: `ProductWebhookProcessor` identifies events by numeric `event_id` field (8 = product changes) instead of string event names.

**Rationale**: Basalam webhooks send `event_id` as an integer, not a string. The existing code checks for `"product.created"` / `"product.updated"` which will never match real payloads.

### 9. Fix imports in ProductWebhookProcessor

**Decision**: Fix the broken import `from src.domains.suppliers.models import SupplierProduct` to `from src.domains.products.models import SupplierProduct`.

**Rationale**: The `suppliers` domain doesn't exist. Product models are in the `products` domain. Also replace raw `session.commit()` with UnitOfWork pattern.

## Risks / Trade-offs

**[Rate limiting]** → Basalam has per-endpoint rate limits (100/min for products). Mitigation: Existing `RateLimiter` class with Redis sliding window is already implemented. Just need to wire it correctly with the right endpoint keys.

**[Token refresh race condition]** → Multiple concurrent requests may try to refresh the same expired token. Mitigation: Use Redis distributed lock (`oauth:refresh:{integration_id}`) with 30-second TTL to serialize refresh attempts.

**[Webhook delivery reliability]** → Basalam may not retry failed webhook deliveries, or retry timing may cause duplicates. Mitigation: Existing `IdempotencyManager` with Redis + DB fallback handles dedup. The `ProcessedEvent` table already tracks event hashes.

**[Credential rotation]** → If `webhook_secret_encryption_key` is rotated, all stored credentials become unreadable. Mitigation: Document that the Fernet key must not be rotated without a migration script. Consider future key rotation endpoint.

**[Basalam API changes]** → The Basalam API may change endpoints or payload formats. Mitigation: `raw_payload` JSONB column stores the original response for re-processing. Mappers can be updated without data loss.

## Migration Plan

1. **Phase 1 — Config & URLs**: Update `config.py` with new URL settings. Update `BasalamClient.BASE_URL` to use `settings.basalam_api_url`. Deploy — no behavior change until Phase 2.

2. **Phase 2 — Database**: Create Alembic migration for `SyncState` table + unique constraint. Deploy migration.

3. **Phase 3 — OAuth**: Fix `BasalamClient` auth methods, fix `IntegrationService.handle_oauth_callback()`, fix `IntegrationService.start_oauth()`. Deploy — OAuth flow now works.

4. **Phase 4 — Product Sync**: Fix `ProductSyncService._fetch_products_page()`, fix mappers. Deploy — products can be synced.

5. **Phase 5 — Webhooks**: Fix webhook registration in `BasalamConnectorAdapter`, fix `ProductWebhookProcessor`. Deploy — webhooks work end-to-end.

**Rollback**: Each phase is independently deployable. If Phase 3 breaks OAuth, the previous integration code (non-functional anyway) is no worse. Feature flags not needed — the existing code doesn't work, so any fix is an improvement.

## Open Questions

1. **Basalam sandbox/test environment**: Do we have a Basalam sandbox vendor account for testing? The OAuth flow requires a real vendor to authorize. Without test credentials, we can only verify URL correctness.
2. **Webhook payload sample data**: The exact webhook payload structure for `event_id=8` is inferred from docs. We should verify by registering a test webhook and inspecting the actual payload shape.
3. **Token expiration timing**: The docs say `expires_in: 31622400` (~1 year). Should we still refresh proactively, or only on 401? Current code refreshes on 401 — this seems sufficient given the long TTL.
