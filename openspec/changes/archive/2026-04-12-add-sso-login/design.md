## Context

The Basalam OAuth shop integration connects vendor marketplace accounts to the dropshipping platform. The flow is: user clicks "Connect Shop" → platform generates auth URL with CSRF state → vendor logs in on Basalam → callback with authorization code → code exchanged for access/refresh tokens → vendor ID fetched → credentials encrypted (Fernet) and stored → webhook registered.

**Current state:**
- Core OAuth flow (start, callback, token exchange) is structurally correct
- Two critical methods are **missing** — `decrypt_from_storage()` and `update_webhook()` — causing `AttributeError` at runtime
- Two overlapping connector implementations exist: `BasalamConnectorAdapter` (hexagonal) and `BasalamConnector` (legacy)
- Integration service calls `BasalamConnectorAdapter` for some paths and `BasalamConnector` via registry for others
- OAuth scopes in code (`vendor.parcel.read vendor.shipping.read`) differ from spec (`customer.order.read`)
- Zero tests exist

**Key files:**
- `src/integrations/shop/connectors/basalam_connector.py` — `BasalamConnector` (used by registry)
- `src/integrations/shop/adapters/basalam.py` — `BasalamConnectorAdapter` (used by integration_service)
- `src/integrations/shop/ports.py` — `ShopConnectorPort` abstract interface
- `src/domains/shops/service/integration_service.py` — orchestration (start_oauth, callback, refresh, webhook)
- `src/domains/shops/service/webhook_secret_service.py` — Fernet encryption (missing `decrypt_from_storage`)

## Goals / Non-Goals

**Goals:**
- Fix the two `AttributeError` bugs so credential decryption and webhook rotation work
- Consolidate connector implementations to a single canonical class
- Add a test suite that covers the full OAuth flow with mocked external calls
- Resolve scope inconsistency between spec and code

**Non-Goals:**
- Adding new OAuth providers (Google, Apple, etc.)
- Adding SSO for user authentication (this is shop integration only)
- Refactoring the entire integration layer architecture
- Changing the API contract (endpoints, request/response shapes)
- Implementing distributed rate limiting (current in-memory is out of scope)

## Decisions

### 1. Add `decrypt_from_storage()` as alias to `decrypt_for_verification()`

Both methods do the same thing — Fernet decrypt a stored value. Rather than adding a new method with different behavior, add `decrypt_from_storage` as an explicit alias that calls `decrypt_for_verification`. This fixes the `AttributeError` without introducing behavioral divergence.

**Alternative considered:** Rename all call sites to use `decrypt_for_verification`. Rejected because `decrypt_from_storage` is a clearer name for credential decryption (vs webhook secret verification). Keep both names, same implementation.

### 2. Add `update_webhook()` to `BasalamConnector` and `ShopConnectorPort`

The integration service's `rotate_webhook_secret()` calls `connector.update_webhook(webhook_id, {secret, url})` at line 883. This method needs to:
1. Be declared as abstract in `ShopConnectorPort`
2. Be implemented in `BasalamConnector` using `BasalamClient.update_webhook()`
3. Be implemented in `BasalamConnectorAdapter` for completeness

Implementation: call the existing `BasalamClient` to PATCH the webhook with new secret/URL.

### 3. Consolidate on `BasalamConnector` (connectors/) as canonical

`BasalamConnector` in `connectors/basalam_connector.py` is the richer implementation — it has all product/order/inventory/webhook methods plus legacy compatibility. `BasalamConnectorAdapter` in `adapters/basalam.py` is thinner and only partially implements the port.

Decision: **Make `BasalamConnectorAdapter` a thin facade** that delegates to `BasalamConnector`. This keeps the hexagonal port satisfied while having one real implementation. Update `integration_service.py` imports to use registry consistently.

**Alternative considered:** Delete `BasalamConnectorAdapter` entirely. Rejected because the adapter layer provides a clean hexagonal boundary — future connectors (Shopify, WooCommerce) would each have their own adapter.

### 4. Resolve scope mismatch — keep code's scopes

Code scopes: `vendor.product.read vendor.parcel.read vendor.shipping.read`
Spec scopes: `vendor.product.read customer.order.read`

The code scopes match what Basalam's API actually requires for the platform's use cases (product sync + order tracking + shipping). The `customer.order.read` scope in the spec appears incorrect — orders come via webhooks, not direct API reads. **Update spec to match code.**

### 5. Test strategy: pytest + httpx mock + fakeredis

- **Unit tests**: Test `WebhookSecretService` (encrypt/decrypt, rotation, signature verification) with no mocks needed
- **Integration tests**: Test `IntegrationService.start_oauth()`, `handle_oauth_callback()`, `refresh_token()` with mocked `BasalamClient` and `fakeredis`
- **Fixtures**: `conftest.py` with async DB session, test client, fake Redis, mock Basalam responses

No external HTTP calls in tests. All Basalam API responses mocked.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Consolidating connectors may not break existing callers of `BasalamConnectorAdapter` beacse code is not on production yet | Adapter not becomes a facade — same interface, delegates to `BasalamConnector` |
| `decrypt_from_storage` alias adds a maintenance burden of two names for one thing | Add deprecation comment pointing to canonical name; remove alias |
| Tests use mocked HTTP — won't catch real Basalam API changes | Add a separate smoke test script (not in CI) that hits sandbox API for manual verification |
| Scope change to spec may confuse if someone already implemented against old spec | Spec is internal; no external consumers. Document the change clearly in delta spec |
