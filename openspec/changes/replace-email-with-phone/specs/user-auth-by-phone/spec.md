## ADDED Requirements

### Requirement: User Registration with Phone Number
The system SHALL allow users to register using an Iranian phone number in the format 09123456789 (11 digits starting with 09).

#### Scenario: Successful registration
- **WHEN** user submits registration form with valid Iranian phone number and password
- **THEN** system creates user account with phone as primary identifier
- **AND** returns success response with user data

#### Scenario: Invalid phone format
- **WHEN** user submits registration with phone number not matching 09123456789 format
- **THEN** system returns validation error with message "Invalid Iranian phone number format"

### Requirement: User Login with Phone Number
The system SHALL authenticate users using their Iranian phone number and password.

#### Scenario: Successful login
- **WHEN** user submits login form with registered phone number and correct password
- **THEN** system returns access token and refresh token
- **AND** user is authenticated for subsequent requests

#### Scenario: Incorrect phone or password
- **WHEN** user submits login with unregistered phone or wrong password
- **THEN** system returns error "Incorrect phone number or password"
