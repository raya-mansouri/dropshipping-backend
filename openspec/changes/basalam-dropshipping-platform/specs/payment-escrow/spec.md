## ADDED Requirements

### Requirement: Payment collection from seller
The system SHALL collect payment from seller at order time.

#### Scenario: Seller payment
- **WHEN** order is created
- **THEN** system SHALL create payment request
- **AND** redirect to payment gateway
- **AND** set payment timeout (15 minutes)

#### Scenario: Payment success
- **WHEN** payment gateway confirms payment
- **THEN** system SHALL update order to seller_paid
- **AND** hold funds in platform wallet
- **AND** notify supplier of pending order

#### Scenario: Payment failure
- **WHEN** payment fails
- **THEN** system SHALL update order status
- **AND** release inventory
- **AND** notify seller

### Requirement: Escrow hold
The system SHALL hold funds until delivery confirmed.

#### Scenario: Funds on hold
- **WHEN** seller payment confirmed
- **THEN** system SHALL hold in escrow
- **AND** NOT release to supplier until conditions met
- **AND** display as "pending" in supplier wallet

### Requirement: Payment release to supplier
The system SHALL release payment after delivery confirmed.

#### Scenario: Delivery confirmed
- **WHEN** order marked as delivery_confirmed
- **AND** no dispute within 72 hours
- **THEN** system SHALL release funds to supplier
- **AND** update wallet balances

#### Scenario: Dispute filed
- **WHEN** dispute filed before release window
- **THEN** system SHALL freeze funds
- **AND** pause release until resolution

### Requirement: Refund processing
The system SHALL handle refunds for cancelled or disputed orders.

#### Scenario: Full refund
- **WHEN** order fully cancelled before shipping
- **THEN** system SHALL refund full amount to seller
- **AND** deduct from supplier if already paid

#### Scenario: Partial refund
- **WHEN** partial refund requested
- **THEN** system SHALL calculate refund amount
- **AND** process refund to seller
- **AND** log refund reason

### Requirement: Wallet reconciliation
The system SHALL reconcile platform wallet with payment gateway.

#### Scenario: Daily reconciliation
- **WHEN** scheduled job runs daily
- **THEN** system SHALL compare records
- **AND** fix any mismatches
- **AND** alert on discrepancies

### Requirement: Payment idempotency
The system SHALL handle duplicate payment webhooks safely.

#### Scenario: Duplicate payment webhook
- **WHEN** same payment webhook received twice
- **THEN** system SHALL process once
- **AND** ignore duplicate
