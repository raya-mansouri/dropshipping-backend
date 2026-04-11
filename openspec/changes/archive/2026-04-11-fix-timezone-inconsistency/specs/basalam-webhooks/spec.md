## MODIFIED Requirements

### Requirement: Process product change webhooks (event_id 8)
The system SHALL process incoming webhooks with `event_id=8` (PRODUCT_CREATE_CHANGES). The webhook payload from Basalam contains the product data that changed. The processor SHALL upsert the product into `SupplierProduct` with variants. Timestamp validation SHALL compare timezone-aware datetimes without stripping timezone info.

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

#### Scenario: Webhook timestamp validation uses timezone-aware comparison
- **WHEN** a webhook arrives with a timestamp in the payload
- **THEN** the system compares the timestamp against `datetime.now(timezone.utc)` directly
- **AND** SHALL NOT strip timezone info via `.replace(tzinfo=None)`
- **AND** SHALL NOT use `datetime.utcfromtimestamp()` to parse the timestamp

## ADDED Requirements

### Requirement: Webhook event log timestamps SHALL be timezone-aware
All datetime columns in webhook event models (`WebhookEventLog`, `WebhookEvent`, `OutgoingWebhookRetry`) SHALL use `DateTime(timezone=True)` and store timezone-aware UTC datetimes.

#### Scenario: Webhook event is logged with aware timestamp
- **WHEN** a webhook event is processed and logged
- **THEN** `processed_at`, `executed_at`, `scheduled_at` are stored as `TIMESTAMPTZ`
- **AND** the values include `tzinfo=timezone.utc`
