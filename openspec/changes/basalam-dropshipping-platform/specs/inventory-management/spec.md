## ADDED Requirements

### Requirement: Inventory is source of truth from supplier
The system SHALL treat supplier inventory as the authoritative source.

#### Scenario: Supplier inventory update via webhook
- **WHEN** inventory webhook received from Basalam
- **THEN** system SHALL update supplier_inventory
- **AND** recalculate available inventory for all sellers

#### Scenario: Seller cannot override inventory
- **WHEN** seller attempts to set inventory manually
- **THEN** system SHALL reject the request
- **AND** return error message

### Requirement: Inventory reservation for orders
The system SHALL reserve inventory when order is created to prevent overselling.

#### Scenario: Order created
- **WHEN** order is created with items
- **THEN** system SHALL reserve inventory for each item
- **AND** decrease available inventory

#### Scenario: Concurrent orders for same item
- **WHEN** two orders created simultaneously for same variant
- **THEN** system SHALL use database locking
- **AND** first order reserves, second fails validation
- **AND** seller notified of insufficient inventory

#### Scenario: Payment confirmed
- **WHEN** payment webhook confirms payment
- **THEN** system SHALL convert reservation to sold
- **AND** update inventory counts

#### Scenario: Order cancelled
- **WHEN** order is cancelled (seller, supplier, or system)
- **THEN** system SHALL release reserved inventory
- **AND** add back to available inventory

### Requirement: Inventory reconciliation
The system SHALL periodically reconcile platform inventory with supplier.

#### Scenario: Reconciliation job runs
- **WHEN** scheduled job executes every 15 minutes
- **THEN** system SHALL fetch current supplier inventory
- **AND** compare with platform records
- **AND** fix any mismatches

#### Scenario: Inventory mismatch detected
- **WHEN** reconciliation finds mismatch
- **THEN** system SHALL log the discrepancy
- **AND** update to match supplier
- **AND** notify affected sellers

### Requirement: Inventory must handle negative stock
The system SHALL properly handle when supplier reports negative or zero inventory.

#### Scenario: Supplier reports zero inventory
- **WHEN** supplier inventory reaches 0
- **THEN** system SHALL set available to 0
- **AND** disable all seller products
- **AND** notify sellers

#### Scenario: Supplier reports negative (should not happen but handle)
- **WHEN** supplier inventory is negative
- **THEN** system SHALL set available to 0
- **AND** log error for investigation

### Requirement: Inventory tracking history
The system SHALL maintain inventory movement history for audit.

#### Scenario: Inventory changes
- **WHEN** inventory is reserved, released, or sold
- **THEN** system SHALL create inventory_movement record
- **AND** store previous and new values
- **AND** store reference to order (if applicable)
