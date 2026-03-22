## MODIFIED Requirements

### Requirement: User Authentication
The system SHALL authenticate users using phone number as primary identifier instead of email.

#### Scenario: Phone-based authentication
- **WHEN** user logs in with phone number and password
- **THEN** system validates against phone-based user records

#### Scenario: Password reset via phone
- **WHEN** user requests password reset
- **THEN** system sends reset instructions via SMS to phone number
