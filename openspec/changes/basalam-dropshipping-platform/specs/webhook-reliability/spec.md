## ADDED Requirements

### Requirement: Webhook receiver
The system SHALL receive webhooks from Basalam and external systems.

#### Scenario: Webhook received
- **WHEN** webhook POST received
- **THEN** system SHALL validate signature
- **AND** create webhook_event record
- **AND** publish to Kafka for processing

### Requirement: Webhook idempotency
The system SHALL process each webhook exactly once.

#### Scenario: Duplicate webhook
- **WHEN** webhook with existing event_id received
- **THEN** system SHALL return success
- **AND** NOT reprocess

#### Scenario: New webhook
- **WHEN** webhook with new event_id received
- **THEN** system SHALL process normally

### Requirement: Webhook validation
The system SHALL validate webhook authenticity.

#### Scenario: Invalid signature
- **WHEN** webhook signature doesn't match
- **THEN** system SHALL reject webhook
- **AND** log security event

### Requirement: Webhook retry logic
The system SHALL retry failed webhook processing.

#### Retry schedule:
- Attempt 1: Immediate
- Attempt 2: 1 minute
- Attempt 3: 5 minutes
- Attempt 4: 15 minutes
- Attempt 5: 1 hour
- Attempt 6: 6 hours

#### Scenario: Processing fails
- **WHEN** webhook processing fails
- **THEN** system SHALL schedule retry
- **AND** increment retry_count

### Requirement: Dead letter queue
The system SHALL move permanently failed webhooks to DLQ.

#### Scenario: Max retries exceeded
- **WHEN** retry_count exceeds limit
- **THEN** system SHALL move to DLQ
- **AND** alert admin
- **AND** require manual intervention

### Requirement: Webhook health monitoring
The system SHALL monitor webhook processing health.

#### Scenario: Webhook lag detected
- **WHEN** webhook queue lag exceeds threshold
- **THEN** system SHALL alert operations
- **AND** show pending webhook count

### Requirement: Manual webhook replay
The system SHALL allow replaying failed webhooks.

#### Scenario: Admin requests replay
- **WHEN** admin triggers webhook replay
- **THEN** system SHALL reprocess from DLQ
- **AND** update status

### Requirement: Webhook processing ordering
The system SHALL process webhooks in order for same entity.

#### Scenario: Multiple webhooks same product
- **WHEN** webhooks arrive out of order
- **THEN** system SHALL process in timestamp order
- **AND** ensure final state is correct
