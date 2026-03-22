## ADDED Requirements

### Requirement: Admin force operations
The system SHALL allow admins to manually override data.

#### Scenario: Force inventory update
- **WHEN** admin sets inventory manually
- **THEN** system SHALL update value
- **AND** log admin action with reason

#### Scenario: Force price update
- **WHEN** admin sets price manually
- **THEN** system SHALL update value
- **AND** override price calculation
- **AND** log admin action

#### Scenario: Force order cancellation
- **WHEN** admin cancels order
- **THEN** system SHALL process cancellation
- **AND** handle refunds if needed
- **AND** log admin action

### Requirement: Fraud detection
The system SHALL detect potential fraud patterns.

#### Fraud signals:
- High cancel rate (>20%)
- Inventory mismatch >10%
- Late shipping rate >30%
- Multiple refund requests
- Suspicious order patterns

#### Scenario: Fraud score high
- **WHEN** supplier/seller fraud score exceeds threshold
- **THEN** system SHALL flag for review
- **AND** notify admin

### Requirement: Dispute resolution
The system SHALL manage disputes between seller and supplier.

#### Scenario: Dispute created
- **WHEN** seller creates dispute
- **THEN** system SHALL notify supplier
- **AND** freeze related payment

#### Scenario: Dispute resolved
- **WHEN** admin resolves dispute
- **THEN** system SHALL apply resolution
- **AND** release or hold funds
- **AND** log decision

### Requirement: Refund management
The system SHALL process refund requests.

#### Scenario: Refund request
- **WHEN** refund requested (seller or admin)
- **THEN** system SHALL validate eligibility
- **AND** process via original payment method

#### Scenario: Partial refund
- **WHEN** partial refund approved
- **THEN** system SHALL calculate amount
- **AND** process partial refund
- **AND** update order status

### Requirement: Supplier score system
The system SHALL track supplier performance.

#### Metrics:
- Late shipping rate
- Cancel rate
- Refund rate
- Complaints

#### Scenario: Score calculation
- **WHEN** periodic score calculation runs
- **THEN** system SHALL calculate scores
- **AND** update supplier rating

### Requirement: Audit log
The system SHALL maintain audit log of all admin actions.

#### Scenario: Admin action
- **WHEN** admin performs action
- **THEN** system SHALL create audit_log entry
- **AND** store old/new values
- **AND** store timestamp and admin ID
