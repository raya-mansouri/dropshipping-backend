## 1. Config & Database

- [ ] 1.1 Add payment gateway config vars to `src/core/config.py`: `payment_gateway`, `payment_env`, `zarinpal_merchant_id` (SecretStr)
- [ ] 1.2 Add Kavenegar config vars to `src/core/config.py`: `kavenegar_api_key` (SecretStr), `kavenegar_sender_number`, `kavenegar_otp_template`
- [ ] 1.3 Add `Transaction` model to `src/domains/payments/models.py` with fields: id (UUID), user_id, order_id, amount (Numeric), gateway (String), authority (String), ref_id (String), status (Enum: pending/completed/failed), extra_data (JSONB), timestamps
- [ ] 1.4 Create Alembic migration for transactions table: `make migrate-create message="add transactions table"`

## 2. Payment Gateway Adapters

- [ ] 2.1 Create `src/integrations/payment/ports.py` with `BasePaymentProvider` ABC defining `create_payment(amount, callback_url, user_phone)` and `verify_payment(authority, amount)` abstract methods
- [ ] 2.2 Create `src/integrations/payment/providers/zarinpal.py` implementing `ZarinpalProvider` with sandbox/production URL switching, `/request.json` and `/verify.json` calls
- [ ] 2.3 Create `src/integrations/payment/factory.py` with `get_payment_provider()` returning the configured provider from `settings.payment_gateway`
- [ ] 2.4 Create `src/integrations/payment/__init__.py` exporting public API

## 3. Payment API Endpoints

- [ ] 3.1 Create `src/domains/payments/schemas.py` — add Pydantic schemas: `PaymentInitiateRequest` (order_id, amount), `PaymentInitiateResponse` (payment_url, authority), `PaymentCallbackRequest` (Authority, Status), `PaymentCallbackResponse` (status, ref_id)
- [ ] 3.2 Create `src/domains/payments/service/payment_gateway_service.py` with `initiate_payment(user_id, order_id, amount)` and `handle_callback(authority, status)` methods using UnitOfWork
- [ ] 3.3 Create `src/api/v1/payments.py` router with `POST /initiate` (authenticated) and `GET /callback` (public, Zarinpal redirect) endpoints
- [ ] 3.4 Register payment router in `src/main.py`

## 4. Kavenegar SMS Enhancement

- [ ] 4.1 Add `send_otp(phone, code)` method to `KavenegarSMSAdapter` using `/verify/lookup.json` with configurable OTP template from `settings.kavenegar_otp_template`
- [ ] 4.2 Add `send_templated(phone, template, tokens)` method using `/verify/lookup.json` with dynamic token parameters
- [ ] 4.3 Update `send()` to use lookup API when `content.template_id` is set, fall back to raw send otherwise
- [ ] 4.4 Fix `base_url` construction — current code uses `self.api_key` as URL prefix instead of `self.base_url`

## 5. Tests

- [ ] 5.1 Unit tests for `ZarinpalProvider.create_payment` and `verify_payment` with mocked httpx responses (success, failure, already verified)
- [ ] 5.2 Unit tests for `PaymentGatewayService.initiate_payment` and `handle_callback` with mocked provider and UnitOfWork
- [ ] 5.3 Unit tests for Kavenegar `send_otp` and `send_templated` with mocked httpx
- [ ] 5.4 Integration test for full payment flow: initiate → callback → verify → Payment status update
