## ADDED Requirements

### Requirement: Kavenegar verify/lookup API for OTP
The existing `KavenegarSMSAdapter` SHALL be enhanced to use Kavenegar's verify/lookup API (`/verify/lookup.json`) for OTP delivery instead of raw `/sms/send.json`. This ensures template-based delivery with higher delivery rates.

#### Scenario: Send OTP code
- **WHEN** system sends an OTP to phone number `09123456789` with code `123456`
- **THEN** adapter calls `https://api.kavenegar.com/v1/{API_KEY}/verify/lookup.json` with `receptor=09123456789`, `template=loginotp`, `token=123456`
- **AND** returns `True` on HTTP 200 with `return.status=200`

#### Scenario: OTP send failure
- **WHEN** Kavenegar returns non-200 status or `return.status != 200`
- **THEN** adapter raises `RuntimeError` with the Kavenegar error message

### Requirement: Templated SMS delivery
The adapter SHALL support sending templated SMS messages using Kavenegar's lookup API with multiple token parameters.

#### Scenario: Send order notification with template
- **WHEN** system sends a templated SMS with template name `neworder` and tokens `token=order_count` and `token2=shop_name`
- **THEN** adapter calls `/verify/lookup.json` with `receptor`, `template=neworder`, `token`, `token2` parameters
- **AND** returns `True` on success

#### Scenario: Missing template name
- **WHEN** `send_templated_sms` is called without a template name in parameters
- **THEN** adapter logs error and returns `False`

### Requirement: Bulk SMS support
The adapter SHALL support sending SMS to multiple recipients via the existing `send_batch` method on `NotificationPort`. For Kavenegar, this uses `/sms/send.json` with comma-separated receptors.

#### Scenario: Batch send to multiple phones
- **WHEN** `send_batch` receives 5 notification requests with phone numbers
- **THEN** adapter sends a single request to `/sms/sendbulk.json` with all receptors
- **AND** returns a list of 5 `NotificationResponse` objects

### Requirement: Connection verification
The adapter SHALL verify Kavenegar API connectivity via the `/account/info.json` endpoint.

#### Scenario: Successful connection check
- **WHEN** `verify_connection` is called and Kavenegar returns HTTP 200
- **THEN** returns `True`

#### Scenario: Failed connection
- **WHEN** `verify_connection` is called and Kavenegar is unreachable
- **THEN** returns `False`

### Requirement: Provider selection via config
The `NotificationManager` SHALL select SMS provider based on `SMS_GATEWAY` config. When set to `kavenegar`, the enhanced Kavenegar adapter is used.

#### Scenario: Config selects Kavenegar
- **WHEN** `SMS_GATEWAY=kavenegar` in config
- **THEN** `NotificationManager` initializes with `KavenegarSMSAdapter` using `KAVENEGAR_API_KEY`, `KAVENEGAR_SENDER_NUMBER`, and `KAVENEGAR_OTP_TEMPLATE` from config

#### Scenario: Missing API key
- **WHEN** `KAVENEGAR_API_KEY` is not configured
- **THEN** application startup logs a warning and SMS sending returns `NotificationResponse(success=False)`
