## Context

The platform has a payments domain (`src/domains/payments/`) with internal Payment, Refund, SupplierPayout, Dispute models tracking escrow flows, but no external payment gateway to collect money from users. The `Payment` model already has `gateway` and `gateway_transaction_id` columns ready for integration.

For SMS, `KavenegarSMSAdapter` exists at `src/integrations/notification/adapters/sms.py` but uses the raw `/sms/send.json` endpoint instead of Kavenegar's verify/lookup API (which supports templates and has higher delivery rates for OTP).

The reference repo (`/home/raya/projects/kalabama-api`) has a clean adapter pattern for both: `BasePaymentProvider` → `ZarinpalProvider` via factory, and `BaseSMSProvider` → `KavenegarProvider`.

## Goals / Non-Goals

**Goals:**
- Zarinpal payment gateway: initiate → redirect → callback → verify flow
- Provider-agnostic adapter pattern for future gateways (Zibal, IDPay)
- Transaction model for gateway-level payment tracking (separate from domain Payment)
- Enhance Kavenegar adapter to use verify/lookup API for OTP and templated SMS
- Config-driven provider selection for both payment and SMS

**Non-Goals:**
- Wallet/balance system (not in scope — payments go directly to gateway)
- Recurring payments or subscriptions
- Payment dashboard/admin UI
- Additional SMS providers beyond Kavenegar (future work)
- Zarinpal v4 GraphQL API (classic REST v4 is simpler and sufficient)

## Decisions

### 1. Payment adapter location: `src/integrations/payment/`

**Decision**: Create a new `src/integrations/payment/` package mirroring the existing `src/integrations/shop/` structure with `ports.py` (abstract), `providers/` (implementations), and `factory.py`.

**Rationale**: Follows the established hexagonal architecture pattern. The integrations layer is where external service adapters live. Keeps payment gateway concerns separate from the domain Payment model.

**Alternative considered**: Putting payment providers inside `src/domains/payments/` — rejected because the domain layer should not depend on external services directly.

### 2. Transaction model as separate from Payment

**Decision**: New `Transaction` model in `src/domains/payments/models.py` alongside existing Payment model. Transaction tracks gateway-level attempts; Payment tracks business-level escrow flow.

**Rationale**: One Payment can have multiple Transaction attempts (user retries payment). Transaction stores gateway-specific fields (authority, ref_id) that don't belong on Payment. After verification, Transaction.ref_id flows to Payment.gateway_transaction_id.

### 3. Zarinpal classic REST v4 (not GraphQL)

**Decision**: Use Zarinpal's `/pg/v4/payment/request.json` and `/verify.json` endpoints.

**Rationale**: The GraphQL API requires OAuth2 token management and is designed for account-level operations (creating terminals, managing documents). The classic REST API is the standard for payment collection — simpler, no token refresh needed, and matches the reference implementation.

### 4. Enhance existing KavenegarSMSAdapter (not replace)

**Decision**: Add `send_otp()` and `send_templated()` methods to the existing `KavenegarSMSAdapter` class using Kavenegar's `/verify/lookup.json` endpoint. Keep existing `send()` for backward compatibility.

**Rationale**: The adapter already implements `NotificationPort`. Adding OTP/lookup methods is additive — no breaking changes. The `send()` method continues to work for non-template SMS via `/sms/send.json`.

### 5. Callback URL pattern

**Decision**: Zarinpal callback goes to `POST /api/v1/payments/callback` with `Authority` and `Status` as query params (Zarinpal appends these to the callback_url). The endpoint handles both GET (Zarinpal redirect) and POST (API call).

**Rationale**: Zarinpal redirects the user back to `callback_url?Authority=xxx&Status=OK`. We need to handle this as a GET endpoint that processes the result and returns a user-friendly page/redirect.

### 6. httpx with shared AsyncClient

**Decision**: Use `httpx.AsyncClient` for both Zarinpal and Kavenegar HTTP calls. Create client instances at module level or via dependency injection rather than per-request.

**Rationale**: Reusing httpx clients avoids creating new TCP connections per request. The reference repo uses a shared `get_http_client()` — we'll follow a similar pattern with FastAPI dependency injection.

## Risks / Trade-offs

**[Zarinpal sandbox instability]** → Sandbox environment can be flaky. Mitigation: clear error messages and logging so issues are obvious during development. Config toggle to production is trivial.

**[Kavenegar rate limits]** → Kavenegar throttles at ~100 req/sec for standard accounts. Mitigation: the existing `send_with_retry` method handles backoff. For bulk, use `send_batch` which sends a single API call.

**[Callback idempotency]** → Zarinpal may call callback multiple times or user may refresh. Mitigation: check Transaction status before processing — if already COMPLETED, return cached result (spec requires this).

**[Amount unit confusion]** → Zarinpal uses Rial, business logic may use Toman. Mitigation: always store amounts in Rial in Transaction model. Add clear docstrings. The Payment model already uses Rial (Numeric 12,2).

**[No webhook from Zarinpal]** → Zarinpal doesn't send server-to-server webhooks, only user redirects. If user closes browser before redirect, payment is verified but we don't know. Mitigation: add a Celery task to poll Zarinpal for pending transactions older than N minutes and verify them proactively.

## Migration Plan

1. Add new config vars to `.env.example` and `Settings` class
2. Add `Transaction` model to `src/domains/payments/models.py`
3. Create Alembic migration: `make migrate-create message="add transactions table"`
4. Create `src/integrations/payment/` package (ports, providers, factory)
5. Enhance `KavenegarSMSAdapter` with OTP/lookup methods
6. Add payment API endpoints in `src/api/v1/payments.py`
7. Register payment router in `src/main.py`
8. Add unit tests for adapters, integration tests for callback flow
9. Rollback: remove payment router from main.py, migration down. No breaking changes to existing code.
