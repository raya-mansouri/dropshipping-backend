## ADDED Requirements

### Requirement: Multi-channel notifications
The system SHALL send notifications via multiple channels.

#### Channels:
- Email
- SMS
- In-app
- Webhook (for seller stores)

#### Scenario: Send order notification
- **WHEN** order received
- **THEN** system SHALL notify supplier
- **AND** notify seller

### Requirement: Key events notifications
The system SHALL notify for these critical events:

#### Events requiring notification:
- order_received
- payment_received
- payment_timeout
- shipment_created
- shipment_delivered
- delivery_confirmed
- order_cancelled
- product_out_of_stock
- product_removed
- price_changed
- inventory_low

#### Scenario: Inventory low notification
- **WHEN** product inventory falls below threshold
- **THEN** system SHALL notify affected sellers
- **AND** suggest alternatives

### Requirement: Notification preferences
The system SHALL allow users to configure notification preferences.

#### Scenario: User configures preferences
- **WHEN** user sets notification preferences
- **THEN** system SHALL store preferences
- **AND** respect channels for each event type

### Requirement: Notification delivery reliability
The system SHALL ensure notifications are delivered.

#### Scenario: Notification delivery fails
- **WHEN** email/SMS fails to deliver
- **THEN** system SHALL retry 3 times
- **AND** log failure
- **AND** show in notification center

### Requirement: In-app notification center
The system SHALL provide in-app notification center.

#### Scenario: View notifications
- **WHEN** user opens notification center
- **THEN** system SHALL show all notifications
- **AND** mark as read when viewed
