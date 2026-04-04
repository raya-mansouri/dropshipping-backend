## ADDED Requirements

### Requirement: Generate OAuth authorization URL
The system SHALL generate a valid Basalam OAuth 2.0 authorization URL using the platform's `client_id`, `redirect_uri`, `scope`, and a cryptographically random `state` parameter. The URL SHALL point to `https://basalam.com/accounts/sso`. The `state` parameter SHALL be stored server-side (Redis with TTL) for CSRF verification during callback.

#### Scenario: Generate authorization URL for a shop
- **WHEN** a shop owner requests to connect their Basalam shop via `POST /shops/{shop_id}/oauth/start`
- **THEN** the system generates an authorization URL at `https://basalam.com/accounts/sso?client_id={CLIENT_ID}&scope=vendor.product.read+customer.order.read&redirect_uri={REDIRECT_URI}&state={RANDOM_STATE}&response_type=code`
- **AND** returns `{authorize_url, state, integration_id}` to the frontend

#### Scenario: State parameter is unique and time-limited
- **WHEN** an authorization URL is generated
- **THEN** the `state` value is a UUID4 or 32-byte random hex string
- **AND** is stored in Redis with a 10-minute TTL keyed by `oauth:state:{state}`

### Requirement: Exchange authorization code for tokens
The system SHALL exchange the OAuth authorization code for `access_token` and `refresh_token` by calling `POST https://auth.basalam.com/oauth/token` with `grant_type=authorization_code`, `client_id`, `client_secret`, `redirect_uri`, and `code`.

#### Scenario: Successful token exchange
- **WHEN** Basalam redirects back with a valid `code` and matching `state`
- **THEN** the system verifies the `state` against the stored value in Redis
- **AND** POSTs to `https://auth.basalam.com/oauth/token` with `grant_type=authorization_code`
- **AND** receives `{access_token, refresh_token, expires_in}`
- **AND** stores tokens encrypted in `ShopIntegration.credentials_encrypted` JSONB field

#### Scenario: Invalid or expired state
- **WHEN** callback is received with a `state` that does not match any stored value
- **THEN** the system returns HTTP 400 with error "Invalid or expired OAuth state"

#### Scenario: Token exchange fails
- **WHEN** Basalam auth server returns an error during code exchange
- **THEN** the system returns HTTP 502 with error "Failed to exchange authorization code with Basalam"

### Requirement: Fetch and store vendor identity
After successful token exchange, the system SHALL call `GET https://openapi.basalam.com/v1/users/me` with the new access token to retrieve the user's `vendor.id`. The `vendor_id` SHALL be stored in `ShopIntegration` for all subsequent API calls.

#### Scenario: Fetch vendor ID after token exchange
- **WHEN** tokens are successfully exchanged
- **THEN** the system calls `GET https://openapi.basalam.com/v1/users/me` with `Authorization: Bearer {access_token}`
- **AND** extracts `vendor.id` from the response `{"id": ..., "vendor": {"id": 12345, "title": "..."}}`
- **AND** stores `vendor_id` in `ShopIntegration.external_shop_id` (as string)
- **AND** marks the integration status as `"connected"`

#### Scenario: User has no vendor account
- **WHEN** the `/users/me` response contains no `vendor` field or `vendor.id` is null
- **THEN** the system returns HTTP 400 with error "No Basalam vendor account found for this user"

### Requirement: Refresh expired access tokens
The system SHALL refresh expired access tokens by calling `POST https://auth.basalam.com/oauth/token` with `grant_type=refresh_token`. New tokens SHALL replace the stored credentials. If refresh fails with 401, the integration SHALL be marked as `"disconnected"`.

#### Scenario: Successful token refresh
- **WHEN** an API call returns 401 and the integration has a `refresh_token`
- **THEN** the system POSTs to `https://auth.basalam.com/oauth/token` with `grant_type=refresh_token`
- **AND** updates `credentials_encrypted` with new `access_token` and `refresh_token`
- **AND** retries the original API call

#### Scenario: Refresh token is expired or revoked
- **WHEN** the refresh token request returns 401
- **THEN** the system updates `ShopIntegration.status` to `"disconnected"`
- **AND** returns an error indicating re-authorization is required

### Requirement: Encrypt stored credentials
The system SHALL encrypt OAuth tokens before storing them in the database using Fernet symmetric encryption with the `webhook_secret_encryption_key` from settings. The `credentials_encrypted` JSONB field SHALL contain `{access_token, refresh_token, vendor_id}`, all encrypted as a single blob.

#### Scenario: Credentials are encrypted at rest
- **WHEN** tokens are stored after OAuth callback
- **THEN** the entire credentials dict is encrypted using Fernet before writing to `credentials_encrypted`
- **AND** decrypted only when needed for API calls

### Requirement: Correct OAuth scopes
The system SHALL request the following scopes when generating the authorization URL: `vendor.product.read vendor.parcel.read vendor.shipping.read`. The scope separator SHALL be a space character (`+` URL-encoded).

#### Scenario: Scopes match Basalam requirements
- **WHEN** the authorization URL is generated
- **THEN** the `scope` parameter contains `vendor.product.read+vendor.parcel.read+vendor.shipping.read`
- **AND** matches the capabilities needed for product sync, order tracking, and shipping
