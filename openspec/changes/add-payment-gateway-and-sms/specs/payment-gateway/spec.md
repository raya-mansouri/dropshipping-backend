## ADDED Requirements

### Requirement: Payment gateway adapter interface
The system SHALL provide a `BasePaymentProvider` abstract class defining the contract for all payment gateway adapters. Every adapter MUST implement `create_payment(amount, callback_url)` and `verify_payment(authority, amount)` methods.

#### Scenario: Factory returns correct provider
- **WHEN** `get_payment_provider()` is called with `PAYMENT_GATEWAY=zarinpal` in config
- **THEN** system returns a `ZarinpalProvider` instance configured with the correct sandbox or production URLs

#### Scenario: Unknown provider rejected
- **WHEN** `get_payment_provider()` is called with an unsupported gateway name
- **THEN** system raises `ValueError` with message indicating the gateway is not supported

### Requirement: Initiate payment via Zarinpal
The system SHALL expose `POST /api/v1/payments/initiate` that creates a payment request with Zarinpal, stores a PENDING transaction, and returns the gateway redirect URL.

#### Scenario: Successful payment initiation
- **WHEN** authenticated user sends `POST /api/v1/payments/initiate` with `order_id` and `amount`
- **THEN** system calls Zarinpal `/request.json` with merchant_id, amount (Rial), callback_url, and user phone
- **AND** Zarinpal returns authority code 100
- **AND** system creates a PENDING `Transaction` record with the authority token
- **AND** response includes `payment_url` for user redirect (e.g. `https://www.zarinpal.com/pg/StartPay/{authority}`)

#### Scenario: Zarinpal rejects payment creation
- **WHEN** Zarinpal `/request.json` returns a non-100 code
- **THEN** system returns HTTP 502 with the Zarinpal error message
- **AND** no Transaction record is created

#### Scenario: Unauthenticated request
- **WHEN** request lacks valid JWT token
- **THEN** system returns HTTP 401

### Requirement: Payment callback verification
The system SHALL expose `POST /api/v1/payments/callback` that verifies the payment with Zarinpal after the user returns from the gateway.

#### Scenario: Successful payment verification
- **WHEN** callback receives `Authority` and `Status=OK` from Zarinpal redirect
- **THEN** system calls Zarinpal `/verify.json` with merchant_id, authority, and amount
- **AND** Zarinpal returns code 100 or 101 (already verified)
- **AND** Transaction status is updated to COMPLETED with `ref_id`
- **AND** the linked domain `Payment` record status is updated to `seller_paid`

#### Scenario: User cancels payment
- **WHEN** callback receives `Status=NOK` or user did not complete payment
- **THEN** Transaction status is updated to FAILED
- **AND** system returns HTTP 200 with cancellation confirmation

#### Scenario: Amount mismatch
- **WHEN** verification amount does not match the original Transaction amount
- **THEN** Transaction status is updated to FAILED with reason "amount_mismatch"
- **AND** system returns HTTP 400

#### Scenario: Already verified transaction
- **WHEN** callback is called for a Transaction already in COMPLETED status
- **THEN** system returns the existing result without calling Zarinpal again (idempotent)

### Requirement: Transaction model for gateway tracking
The system SHALL maintain a `Transaction` model separate from the domain `Payment` to track individual gateway payment attempts. Fields: `id`, `user_id`, `order_id`, `amount` (Rial), `gateway` (provider name), `authority` (gateway token), `ref_id` (gateway reference), `status` (pending/completed/failed), `extra_data` (JSONB for gateway response).

#### Scenario: Transaction links to Payment
- **WHEN** a Transaction is created for a payment initiation
- **THEN** it references both `user_id` and `order_id` for audit trail
- **AND** `gateway_transaction_id` on the `Payment` model is updated with the Transaction's `ref_id` after verification

### Requirement: Sandbox/production toggle
The system SHALL switch between Zarinpal sandbox and production URLs based on `PAYMENT_ENV` config value. Sandbox mode SHALL use a fixed test merchant ID. Production mode SHALL use `ZARINPAL_MERCHANT_ID` from config.

#### Scenario: Sandbox mode
- **WHEN** `PAYMENT_ENV=sandbox`
- **THEN** all API calls go to `sandbox.zarinpal.com` with the sandbox merchant ID

#### Scenario: Production mode
- **WHEN** `PAYMENT_ENV=production`
- **THEN** all API calls go to `api.zarinpal.com` / `www.zarinpal.com` with `ZARINPAL_MERCHANT_ID`
