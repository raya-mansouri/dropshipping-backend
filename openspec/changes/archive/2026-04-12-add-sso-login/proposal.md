## Why

The Basalam OAuth shop integration has critical runtime bugs that prevent credential decryption and webhook secret rotation from working. Zero tests exist. The spec and implementation are out of sync on scopes and connector structure. These issues will surface in production when shops try to connect or when webhook secrets rotate.

## What Changes

- Fix missing `decrypt_from_storage()` method in `WebhookSecretService` — causes `AttributeError` on every credential read
- Fix missing `update_webhook()` method on `BasalamConnector` and `ShopConnectorPort` — causes `AttributeError` during webhook secret rotation
- Align OAuth scopes between spec and code — resolve `customer.order.read` vs `vendor.parcel.read vendor.shipping.read` mismatch
- Consolidate dual connector implementations — `BasalamConnectorAdapter` (adapters/) and `BasalamConnector` (connectors/) serve overlapping roles; pick one canonical path
- Add comprehensive test suite covering the full OAuth flow, token refresh, credential encryption, and webhook lifecycle

## Capabilities

### New Capabilities
- `oauth-shop-connect`: End-to-end OAuth2 flow for connecting Basalam shops — authorization URL generation, state management, code exchange, vendor identity fetch, credential encryption, token refresh, and webhook registration/rotation

### Modified Capabilities
- `basalam-oauth`: Fix scope mismatch, clarify that scopes include order/product/shipping read access per actual API requirements

## Impact

- **Code**: `src/integrations/shop/connectors/basalam_connector.py`, `src/integrations/shop/adapters/basalam.py`, `src/integrations/shop/ports.py`, `src/domains/shops/service/integration_service.py`, `src/domains/shops/service/webhook_secret_service.py`
- **API**: Existing endpoints `POST /shops/{id}/oauth/start` and `POST /shops/{id}/oauth/callback` — no API contract changes, only bug fixes
- **Dependencies**: No new dependencies — uses existing `httpx`, `redis`, `cryptography.fernet`
- **Tests**: New `tests/` directory with integration tests for OAuth flow, encryption, and token refresh
