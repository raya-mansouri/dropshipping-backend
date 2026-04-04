## ADDED Requirements

### Requirement: Register webhook with Basalam webhook service
The system SHALL register webhooks by calling `POST https://webhook.basalam.com/v1/webhooks` with the vendor's access token. The request body SHALL contain `event_ids` as a JSON array of numeric IDs, `url` as the public endpoint, `request_method: "POST"`, and `is_active: true`. The system SHALL use `register_me: true` on first registration to auto-create a webhook service.

#### Scenario: Register webhook for product change events
- **WHEN** a shop integration is first connected
- **THEN** the system calls `POST https://webhook.basalam.com/v1/webhooks` with `Authorization: Bearer {vendor_access_token}`
- **AND** body `{"event_ids": [8, 5, 7], "request_method": "POST", "url": "https://{OUR_DOMAIN}/api/v1/webhooks/basalam/{integration_id}", "is_active": true, "register_me": true}`
- **AND** receives `{id, service_id, url, events, is_active}`
- **AND** stores the returned `id` as `ShopIntegration.webhook_id`

#### Scenario: Webhook registration fails
- **WHEN** the webhook registration API returns 4xx or 5xx
- **THEN** the integration is still created with `webhook_status="not_registered"`
- **AND** the error is logged with integration_id context
- **AND** a retry can be triggered later via the integration service

### Requirement: Use numeric event IDs for Basalam webhooks
The system SHALL use Basalam's numeric event IDs, not string event names:
- `8` = `PRODUCT_CREATE_CHANGES` (product created or modified)
- `5` = `VENDOR_NEW_ORDER` (new sale order)
- `7` = `VENDOR_PARCEL_CHANGES` (parcel/order status change)
- `3` = `VENDOR_ORDER_ITEM_CHANGES` (order item status change)

#### Scenario: Subscribe to product events only
- **WHEN** registering a webhook for product sync only
- **THEN** `event_ids` is `[8]` in the request body

#### Scenario: Subscribe to all vendor events
- **WHEN** registering a webhook for full integration (products + orders + inventory)
- **THEN** `event_ids` is `[8, 5, 7, 3]` in the request body

### Requirement: Subscribe user to webhook with their own token
After creating the webhook, the system SHALL subscribe the vendor's user to the webhook by calling `POST https://webhook.basalam.com/v1/webhooks/{webhook_id}/subscribe` with the vendor's own access token (not the platform token). This is the 2-step webhook subscription flow required by Basalam.

#### Scenario: Subscribe user to webhook
- **WHEN** a webhook is created with `id=12345`
- **THEN** the system calls `POST https://webhook.basalam.com/v1/webhooks/12345/subscribe` with `Authorization: Bearer {vendor_access_token}`
- **AND** the vendor's events start flowing to the registered URL

### Requirement: Process product change webhooks (event_id 8)
The system SHALL process incoming webhooks with `event_id=8` (PRODUCT_CREATE_CHANGES). The webhook payload from Basalam contains the product data that changed. The processor SHALL upsert the product into `SupplierProduct` with variants.

#### Scenario: Product created on Basalam triggers webhook
- **WHEN** a POST arrives at `/api/v1/webhooks/basalam/{integration_id}` with `event_id=8`
- **THEN** the system verifies the webhook signature (HMAC-SHA256)
- **AND** checks idempotency via `ProcessedEvent`
- **AND** extracts product data from the webhook payload
- **AND** creates or updates `SupplierProduct` + `SupplierVariant` in the database
- **AND** returns HTTP 200

#### Scenario: Duplicate webhook is handled idempotently
- **WHEN** the same webhook event is received twice
- **THEN** the system detects the duplicate via `event_id` + `payload_hash` in `ProcessedEvent`
- **AND** returns HTTP 200 without processing

### Requirement: Webhook signature verification
The system SHALL verify webhook signatures using HMAC-SHA256 with the webhook secret stored encrypted in `ShopIntegration.webhook_secret_encrypted`. The signature is computed over the raw request body. Both the current secret and the previous secret (during 24-hour rotation window) SHALL be accepted.

#### Scenario: Valid signature with current secret
- **WHEN** a webhook arrives with `X-Basalam-Signature: sha256={hex}`
- **THEN** the system decrypts the current webhook secret
- **AND** computes `HMAC-SHA256(raw_body, secret)` and compares with the provided signature
- **AND** accepts the webhook if they match

#### Scenario: Valid signature with rotated previous secret
- **WHEN** a webhook arrives during the 24-hour rotation window
- **THEN** the system also tries the previous secret from `webhook_previous_secret_encrypted`
- **AND** accepts the webhook if either secret matches

#### Scenario: Invalid signature
- **WHEN** the computed signature does not match either current or previous secret
- **THEN** the system returns HTTP 401 and logs a security warning

### Requirement: Unregister webhooks on disconnect
The system SHALL call `DELETE https://webhook.basalam.com/v1/webhooks/{webhook_id}` with the vendor's access token when an integration is disconnected. The integration's `webhook_status` SHALL be set to `"inactive"`.

#### Scenario: Disconnect removes webhook
- **WHEN** a shop owner disconnects their Basalam integration
- **THEN** the system calls `DELETE https://webhook.basalam.com/v1/webhooks/{webhook_id}` with the vendor's token
- **AND** sets `ShopIntegration.webhook_status` to `"inactive"` and `status` to `"disconnected"`

#### Scenario: Webhook deletion fails on disconnect
- **WHEN** the webhook deletion API returns an error
- **THEN** the system still disconnects the integration with `webhook_status="cleanup_failed"`
- **AND** logs a warning about the orphaned webhook

### Requirement: Webhook URL is configurable per environment
The webhook callback URL SHALL be constructed from `settings.webhook_base_url` (or `settings.base_url` as fallback). The URL format SHALL be `{base_url}/api/v1/webhooks/basalam/{integration_id}`.

#### Scenario: Webhook URL uses configured base URL
- **WHEN** registering a webhook for `integration_id=abc-123`
- **THEN** the URL is `{settings.webhook_base_url}/api/v1/webhooks/basalam/abc-123`
- **AND** uses `settings.base_url` as fallback if `webhook_base_url` is not set
