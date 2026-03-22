## MODIFIED Requirements

### Requirement: User Profile Fields
User profiles SHALL use phone numbers as primary contact identifier instead of email.

#### Scenario: Profile display
- **WHEN** user views their profile
- **THEN** phone number is shown as primary contact field

#### Scenario: Profile update
- **WHEN** user updates profile with new phone number
- **THEN** system validates phone format and updates record
