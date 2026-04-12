## Why

Platform tracks payments internally but has no external gateway to collect money. SMS needs a proper Kavenegar adapter.

## What Changes

- Add Zarinpal payment gateway (adapter pattern, factory for future providers)
  - POST /api/v1/payments/initiate, POST /api/v1/payments/callback
  - Initiate → redirect → callback → verify → update internal payment
- Add Kavenegar SMS adapter following NotificationPort interface
  - OTP delivery, templated SMS, bulk SMS
- New Transaction model for gateway payment attempts

## Capabilities

### New Capabilities
- payment-gateway: External payment gateway — initiate, callback, verify. Provider-agnostic adapter (Zarinpal first).
- kavenegar-sms: Kavenegar SMS adapter — OTP, templated notifications, bulk SMS via NotificationPort.

### Modified Capabilities
_(none)_

## Impact

- New: src/integrations/payment/, Kavenegar SMS adapter, Transaction model + migration
- Modified: src/core/config.py, notification adapters, payment webhook processor
- API: 2 new endpoints, DB: new transactions table
- Config: PAYMENT_GATEWAY, PAYMENT_ENV, ZARINPAL_MERCHANT_ID, KAVENEGAR_API_KEY, KAVENEGAR_SENDER_NUMBER, KAVENEGAR_OTP_TEMPLATE
- Reference: /home/raya/projects/kalabama-api
