## ADDED Requirements

### Requirement: Shipping methods from supplier
The system SHALL sync available shipping methods from supplier's Basalam account.

#### Scenario: Fetch shipping methods
- **WHEN** supplier connects shop
- **THEN** system SHALL fetch available shipping methods
- **AND** store in supplier_shipping_rules

#### Scenario: Shipping method disabled
- **WHEN** supplier disables shipping method
- **THEN** system SHALL update status
- **AND** notify affected sellers

### Requirement: Shipment creation
The system SHALL create shipments when order is paid.

#### Scenario: Order paid - create shipment
- **WHEN** payment confirmed
- **THEN** system SHALL create shipment record
- **AND** send to supplier via Basalam API

#### Scenario: Shipment creation fails
- **WHEN** Basalam API fails to create shipment
- **THEN** system SHALL retry 3 times
- **AND** notify supplier manually if fails

### Requirement: Tracking and status updates
The system SHALL track shipment status and update order accordingly.

#### Scenario: Tracking code received
- **WHEN** supplier provides tracking code
- **THEN** system SHALL update shipment record
- **AND** show tracking to seller/customer

#### Scenario: Shipment in transit
- **WHEN** tracking shows in_transit
- **THEN** system SHALL update order status
- **AND** notify seller

#### Scenario: Shipment delivered
- **WHEN** tracking shows delivered
- **THEN** system SHALL update order to delivered
- **AND** start 72-hour confirmation window

### Requirement: Delivery confirmation
The system SHALL confirm delivery through multiple methods.

#### Scenario: Carrier confirms delivery
- **WHEN** carrier status = delivered
- **THEN** system SHALL update order to delivered
- **AND** start auto-confirm timer

#### Scenario: Customer confirms receipt
- **WHEN** customer clicks "Received"
- **THEN** system SHALL immediately confirm delivery
- **AND** trigger payment release

#### Scenario: Auto-confirm timeout
- **WHEN** delivered for 72 hours with no dispute
- **THEN** system SHALL auto-confirm delivery
- **AND** release payment to supplier

### Requirement: Shipping deadline
The system SHALL enforce shipping deadlines to prevent delays.

#### Scenario: Supplier misses deadline
- **WHEN** supplier doesn't ship within SLA
- **THEN** system SHALL apply penalty
- **AND** notify seller
- **AND** log for supplier score

### Requirement: Delivery failure handling
The system SHALL handle failed deliveries.

#### Scenario: Delivery failed
- **WHEN** package returned or failed delivery
- **THEN** system SHALL update order status
- **AND** initiate return if applicable
- **AND** process refund if needed

### Requirement: Multiple shipping types
The system SHALL handle different shipping types from Basalam.

## MODIFIED Requirements

### Requirement: Basalam shipping types
The system SHALL support all Basalam shipping methods.

#### Scenario: Basalam Post shipping
- **WHEN** order uses basalam_post shipping
- **THEN** system SHALL use Basalam's shipping network
- **AND** fetch tracking from Basalam API

#### Scenario: Supplier's own shipping
- **WHEN** order uses supplier_shipping
- **THEN** system SHALL use supplier's configured shipping
- **AND** supplier provides tracking code manually

#### Scenario: Express shipping
- **WHEN** order uses express shipping
- **THEN** system SHALL prioritize fulfillment
- **AND** apply express SLA (24-48 hours)

#### Scenario: Pickup shipping
- **WHEN** order uses pickup shipping
- **THEN** system SHALL show pickup location
- **AND** mark as ready for pickup when available
- **AND** no tracking code needed

#### Scenario: Custom shipping
- **WHEN** supplier configures custom shipping
- **THEN** system SHALL use supplier_shipping_profiles
- **AND** calculate cost based on regions

### Requirement: Shipping SLA enforcement
The system SHALL track and enforce shipping deadlines.

#### Scenario: Standard shipping SLA
- **WHEN** order uses standard shipping
- **AND** supplier doesn't ship within 48 hours
- **THEN** system SHALL flag as delayed
- **AND** notify seller
- **AND** increase supplier delay score

#### Scenario: Express shipping SLA
- **WHEN** order uses express shipping
- **AND** supplier doesn't ship within 24 hours
- **THEN** system SHALL flag as delayed
- **AND** apply penalty
- **AND** notify seller immediately

### Requirement: Shipping cost calculation
The system SHALL calculate shipping costs based on supplier profiles.

#### Scenario: Calculate shipping cost
- **WHEN** order is being created
- **THEN** system SHALL calculate shipping based on:
  - Supplier shipping profile
  - Destination region
  - Shipping method selected
  - Product weight/dimensions
- **AND** add to order total

#### Scenario: Free shipping threshold
- **WHEN** order total exceeds supplier's free shipping threshold
- **THEN** system SHALL set shipping_cost = 0
- **AND** apply to order
