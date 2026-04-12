## Requirements

### Requirement: Generate OAuth authorization URL with CSRF state
The system SHALL generate a Basalam OAuth 2.0 authorization URL using `client_id`, `redirect_uri`, `scope`, and a cryptographically random `state` parameter. The URL SHALL point to `https://basalam.com/accounts/sso`. The `state` SHALL be stored in Redis with key `oauth:state:{state}` and a 10-minute TTL, containing `{"shop_id": "<uuid>", "platform_code": "<code>"}` as JSON.

#### Scenario: Generate authorization URL for a shop
- **WHEN** a shop owner requests `POST /shops/{shop_id}/oauth/start` with a valid `platform_code`
- **THEN** the system generates a URL at `https://basalam.com/accounts/sso?client_id={CLIENT_ID}&scope={SCOPES}&redirect_uri={REDIRECT_URI}&state={STATE}&response_type=code`
- **AND** returns `{"authorize_url": "<url>", "state": "<state>", "integration_id": "<uuid>"}`

#### Scenario: State is cryptographically random and time-limited
- **WHEN** an authorization URL is generated
- **THEN** the `state` value is a UUID4 hex string (32 chars)
- **AND** is stored in Redis with key `oauth:state:{state}` and TTL of 600 seconds

#### Scenario: State is single-use
- **WHEN** the callback consumes a state via `oauth:state:{state}`
- **THEN** the key is deleted from Redis immediately after retrieval

### Requirement: Exchange authorization code for encrypted credentials
The system SHALL verify the `state` against Redis, exchange the authorization code for tokens via `POST https://auth.basalam.com/oauth/token` with `grant_type=authorization_code`, encrypt the credentials with Fernet, and store them in `ShopIntegration.credentials_encrypted` as JSONB `{"encrypted": "<fernet_blob>"}`.

#### Scenario: Successful token exchange and credential storage
- **WHEN** Basalam redirects back with a valid `code` and matching `state`
- **THEN** the system verifies the `state` against Redis and deletes it
- **AND** POSTs to `https://auth.basalam.com/oauth/token` with `grant_type=authorization_code`
- **AND** receives `{access_token, refresh_token, expires_in}`
- **AND** encrypts the JSON blob `{"access_token": "...", "refresh_token": "...", "vendor_id": "..."}` with Fernet
- **AND** stores `{"encrypted": "<fernet_blob>"}` in `credentials_encrypted`

#### Scenario: Invalid or expired state
- **WHEN** callback is received with a `state` not found in Redis
- **THEN** the system returns HTTP 400 with error "Invalid or expired OAuth state"

#### Scenario: State does not match shop
- **WHEN** callback is received with a `state` whose stored `shop_id` does not match the request `shop_id`
- **THEN** the system returns HTTP 400 with error "OAuth state does not match shop"

#### Scenario: Token exchange fails at Basalam
- **WHEN** Basalam auth server returns an error during code exchange
- **THEN** the system returns HTTP 502 with error "Failed to exchange authorization code with Basalam: {detail}"

### Requirement: Fetch and store vendor identity
After successful token exchange, the system SHALL call `GET https://openapi.basalam.com/v1/users/me` with `Authorization: Bearer {access_token}` to retrieve the vendor ID. The `vendor_id` SHALL be stored in `ShopIntegration.external_shop_id` and the integration status SHALL be set to `"connected"`.

#### Scenario: Fetch vendor ID after token exchange
- **WHEN** tokens are successfully exchanged
- **THEN** the system calls `GET /v1/users/me` with the new access token
- **AND** extracts `vendor.id` from `{"id": ..., "vendor": {"id": 12345, "title": "..."}}`
- **AND** stores `vendor_id` as string in `external_shop_id`
- **AND** sets integration status to `"connected"`

#### Scenario: User has no vendor account
- **WHEN** the `/users/me` response contains no `vendor` field or `vendor.id` is null
- **THEN** the system returns HTTP 400 with error "No Basalam vendor account found for this user"

### Requirement: Decrypt stored credentials for API calls
The system SHALL provide a `decrypt_from_storage()` method on `WebhookSecretService` that decrypts Fernet-encrypted credential blobs stored in `credentials_encrypted`. This method SHALL be functionally equivalent to `decrypt_for_verification()`.

#### Scenario: Decrypt credentials for webhook registration
- **WHEN** the system needs the access token for webhook registration or API calls
- **THEN** it calls `secret_service.decrypt_from_storage(encrypted_blob)` to get the JSON string
- **AND** parses the JSON to extract `access_token`, `refresh_token`, `vendor_id`

#### Scenario: Decryption fails with wrong key
- **WHEN** a credential blob is encrypted with a different Fernet key than configured
- **THEN** `decrypt_from_storage()` raises `InvalidToken` and the caller returns an error

### Requirement: Refresh expired access tokens with distributed lock
The system SHALL refresh expired access tokens by calling `POST https://auth.basalam.com/oauth/token` with `grant_type=refresh_token`. A Redis distributed lock with key `oauth:refresh:{integration_id}` (TTL 30s) SHALL prevent concurrent refreshes. On 401 from refresh endpoint, the integration SHALL be marked `"disconnected"`.

#### Scenario: Successful token refresh
- **WHEN** an API call returns 401 and the integration has a `refresh_token`
- **THEN** the system acquires Redis lock `oauth:refresh:{integration_id}`
- **AND** decrypts current credentials to get the refresh token
- **AND** POSTs to token endpoint with `grant_type=refresh_token`
- **AND** re-encrypts new credentials with Fernet
- **AND** releases the Redis lock

#### Scenario: Concurrent refresh attempt
- **WHEN** another process already holds the refresh lock
- **THEN** the system waits 2 seconds and returns the current integration state

#### Scenario: Refresh token expired or revoked
- **WHEN** the refresh token request returns 401
- **THEN** the system updates `ShopIntegration.status` to `"disconnected"`
- **AND** stores `"last_error"` with the failure detail

### Requirement: Webhook secret rotation via connector update
The system SHALL rotate webhook secrets by generating a new secret, calling `connector.update_webhook(webhook_id, {secret, url})` to update the platform, and storing both old and new encrypted secrets for a 24-hour overlap period.

#### Scenario: Successful secret rotation
- **WHEN** `rotate_webhook_secret()` is called for a connected integration
- **THEN** a new 32-byte secret is generated and encrypted with Fernet
- **AND** `connector.update_webhook(webhook_id, {"secret": new_secret, "url": webhook_url})` is called
- **AND** `webhook_secret_encrypted` is updated with the new encrypted secret
- **AND** `webhook_previous_secret_encrypted` stores the old encrypted secret
- **AND** `webhook_previous_secret_expires_at` is set to 24 hours from now

#### Scenario: Rotation fails at platform
- **WHEN** `connector.update_webhook()` raises an exception
- **THEN** the database is NOT updated (no new secret stored)
- **AND** a `WebhookRegistrationError` is raised

### Requirement: Connector update_webhook method
The `BasalamConnector` SHALL implement `update_webhook(webhook_id, config)` that updates the webhook secret and/or URL on the Basalam platform via the API client.

#### Scenario: Update webhook on Basalam
- **WHEN** `update_webhook(webhook_id, {"secret": "...", "url": "..."})` is called
- **THEN** the connector calls `BasalamClient` to update the webhook with the new configuration
- **AND** returns `True` on success

#### Scenario: Update webhook fails
- **WHEN** the API call to update the webhook fails
- **THEN** the connector raises the underlying exception

### Requirement: OAuth scopes match API needs
The system SHALL request scopes `vendor.product.read vendor.parcel.read vendor.shipping.read` when generating the authorization URL. These cover product sync, order/parcel tracking, and shipping operations.

#### Scenario: Scopes in authorization URL
- **WHEN** the authorization URL is generated
- **THEN** the `scope` parameter contains `vendor.product.read vendor.parcel.read vendor.shipping.read` (space-separated, `+` URL-encoded)

### Requirement: Comprehensive test coverage for OAuth flow
The system SHALL have tests covering all OAuth scenarios with mocked external calls (Basalam API, Redis).

#### Scenario: Unit tests for WebhookSecretService
- **WHEN** the test suite runs
- **THEN** `encrypt_for_storage` / `decrypt_from_storage` roundtrip succeeds
- **AND** `decrypt_from_storage` with wrong key raises `InvalidToken`
- **AND** `rotate_secret` produces valid new secret and sets 24h expiry
- **AND** `verify_signature` validates HMAC-SHA256 signatures correctly

#### Scenario: Integration tests for OAuth start
- **WHEN** `POST /shops/{shop_id}/oauth/start` is called
- **THEN** a valid authorization URL is generated
- **AND** state is stored in mock Redis with 600s TTL
- **AND** a pending integration is created

#### Scenario: Integration tests for OAuth callback
- **WHEN** `POST /shops/{shop_id}/oauth/callback` is called with valid code and state
- **THEN** state is verified and deleted from Redis
- **AND** token exchange is called with correct parameters
- **AND** vendor info is fetched and stored
- **AND** credentials are encrypted and stored in DB

#### Scenario: Integration tests for token refresh
- **WHEN** token refresh is triggered for an integration with expired tokens
- **THEN** Redis lock is acquired
- **AND** new tokens are obtained and re-encrypted
- **AND** lock is released
