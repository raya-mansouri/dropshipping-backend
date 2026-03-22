## ADDED Requirements

### Requirement: Iranian Phone Number Format Validation
The system SHALL validate phone numbers as exactly 11 digits starting with 09.

#### Scenario: Valid phone number
- **WHEN** input is "09123456789" (11 digits, starts with 09)
- **THEN** validation passes

#### Scenario: Invalid length
- **WHEN** input is "0912345678" (10 digits)
- **THEN** validation fails with "Phone number must be exactly 11 digits"

#### Scenario: Invalid prefix
- **WHEN** input is "08123456789" (starts with 08)
- **THEN** validation fails with "Phone number must start with 09"

#### Scenario: Non-numeric characters
- **WHEN** input contains letters like "091234abcd9"
- **THEN** validation fails with "Phone number must contain only digits"
