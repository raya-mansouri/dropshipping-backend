## 1. Bug Fixes

- [x] 1.1 Add `decrypt_from_storage()` method to `WebhookSecretService` — alias to `decrypt_for_verification()`, with deprecation docstring
- [x] 1.2 Add `update_webhook(webhook_id, config)` abstract method to `ShopConnectorPort` in `src/integrations/shop/ports.py`
- [x] 1.3 Implement `update_webhook()` on `BasalamConnector` — delegates to `BasalamClient` to PATCH webhook with new secret/URL
- [x] 1.4 Implement `update_webhook()` on `BasalamConnectorAdapter` — delegates to `BasalamConnector.update_webhook()`

## 2. Spec Alignment

- [x] 2.1 Update `openspec/specs/basalam-oauth/spec.md` — change scopes from `customer.order.read` to `vendor.parcel.read vendor.shipping.read` to match code

## 3. Test Infrastructure

- [x] 3.1 Create `tests/conftest.py` — async DB session fixture, test client, fake Redis, mock Basalam API responses
- [x] 3.2 Create `tests/unit/__init__.py` and `tests/integration/__init__.py`

## 4. Unit Tests — WebhookSecretService

- [x] 4.1 Test `encrypt_for_storage` / `decrypt_from_storage` roundtrip — encrypt then decrypt produces original value
- [x] 4.2 Test `decrypt_from_storage` raises `InvalidToken` with wrong Fernet key
- [x] 4.3 Test `decrypt_from_storage` raises `ValueError` on empty input
- [x] 4.4 Test `rotate_secret` — generates new secret, sets 24h expiry, keeps old secret encryptable
- [x] 4.5 Test `verify_signature` — validates `sha256=<hex>` format correctly
- [x] 4.6 Test `verify_signature` — validates `t=<ts>,sha256=<hex>` format with timestamp tolerance
- [x] 4.7 Test `verify_signature` — rejects expired timestamps and mismatched signatures

## 5. Integration Tests — OAuth Start

- [x] 5.1 Test `start_oauth` returns valid authorization URL with correct client_id, scopes, state, redirect_uri
- [x] 5.2 Test `start_oauth` stores state in Redis with 600s TTL and correct shop_id/platform_code payload
- [x] 5.3 Test `start_oauth` creates a pending integration record in DB

## 6. Integration Tests — OAuth Callback

- [x] 6.1 Test successful callback — state verified, code exchanged, vendor fetched, credentials encrypted and stored, integration marked "connected"
- [x] 6.2 Test callback with invalid state — returns 400 "Invalid or expired OAuth state"
- [x] 6.3 Test callback with state mismatch — returns 400 "OAuth state does not match shop"
- [x] 6.4 Test callback with token exchange failure — returns 502 with error detail
- [x] 6.5 Test callback with no vendor account — returns 400 "No Basalam vendor account found"
- [x] 6.6 Test state is deleted from Redis after successful callback (single-use)

## 7. Integration Tests — Token Refresh

- [x] 7.1 Test successful refresh — new tokens obtained, re-encrypted, old tokens replaced
- [x] 7.2 Test concurrent refresh — second caller gets current state (lock held)
- [x] 7.3 Test refresh with expired/revoked token — integration marked "disconnected" with error detail

## 8. Integration Tests — Webhook Secret Rotation

- [x] 8.1 Test successful rotation — new secret generated, `update_webhook` called, both secrets stored with 24h overlap
- [x] 8.2 Test rotation failure — `update_webhook` raises exception, DB not updated, `WebhookRegistrationError` raised
- [x] 8.3 Test rotation on disconnected integration — returns ValueError
