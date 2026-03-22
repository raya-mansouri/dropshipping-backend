## ADDED Requirements

### Requirement: Order creation
The system SHALL create orders when received from seller store.

#### Scenario: New order from seller
- **WHEN** seller store sends order via API
- **THEN** system SHALL validate inventory
- **AND** create order with items
- **AND** reserve inventory
- **AND** create order_supplier_groups

#### Scenario: Inventory validation fails
- **WHEN** any item has insufficient inventory
- **THEN** system SHALL reject order
- **AND** return error with unavailable items

#### Scenario: Order with multiple suppliers
- **WHEN** order contains items from multiple suppliers
- **THEN** system SHALL create separate supplier_groups
- **AND** each group can have independent status

### Requirement: Order state machine
The system SHALL manage order through defined states.

#### States:
- order_created
- inventory_reserved
- seller_paid
- supplier_paid_hold
- supplier_shipped
- in_transit
- delivered
- delivery_confirmed
- completed
- cancelled

#### Scenario: Order state transition
- **WHEN** valid event occurs for order
- **THEN** system SHALL transition to new state
- **AND** create order_history record
- **AND** trigger relevant notifications

### Requirement: Order cancellation
The system SHALL handle order cancellation from multiple sources.

#### Scenario: Seller cancels unpaid order
- **WHEN** seller cancels order before payment
- **THEN** system SHALL release inventory reservations
- **AND** update order status to cancelled

#### Scenario: Seller cancels paid order
- **WHEN** seller cancels after payment but before shipping
- **THEN** system SHALL initiate refund
- **AND** release inventory
- **AND** notify supplier

#### Scenario: Payment timeout
- **WHEN** payment not received within 15 minutes
- **THEN** system SHALL cancel order
- **AND** release inventory retention

### Requirement: Order history and audit
The system SHALL maintain complete order history.

#### Scenario: Order status changes
- **WHEN** order status changes
- **THEN** system SHALL create order_history record
- **AND** store old status, new status, timestamp, actor

### Requirement: Order splitting
The system SHALL handle splitting orders by supplier.

#### Scenario: Order split by supplier
- **WHEN** order has items from 3 suppliers
- **THEN** system SHALL create order_supplier_group for each
- **AND** each group processed independently

#### Scenario: Partial shipment
- **WHEN** one supplier ships but another delays
- **THEN** system SHALL track each group status
- **AND** order complete when all groups delivered

## MODIFIED Requirements

### Requirement: Delivery confirmation logic
The system SHALL confirm delivery through multiple methods and release payment appropriately.

#### Scenario: Delivery confirmed by carrier tracking
- **WHEN** carrier status shows "delivered"
- **THEN** system SHALL update order status to delivered
- **AND** start 72-hour dispute window timer

#### Scenario: Customer confirms receipt
- **WHEN** customer clicks "Order Received" button
- **THEN** system SHALL immediately confirm delivery
- **AND** trigger payment release to supplier
- **AND** update order status to delivery_confirmed

#### Scenario: Auto-confirm after timeout
- **WHEN** order status is delivered AND 72 hours pass without dispute
- **THEN** system SHALL auto-confirm delivery
- **AND** release payment to supplier
- **AND** update order status to delivery_confirmed

#### Scenario: High-value order auto-confirm
- **WHEN** order total exceeds threshold (high-value)
- **AND** order is delivered
- **THEN** system SHALL use 7-day dispute window
- **AND** auto-confirm after 7 days

#### Scenario: Dispute filed during window
- **WHEN** customer opens dispute before confirmation
- **THEN** system SHALL freeze payment release
- **AND** pause auto-confirm timer
- **AND** set order status to disputed

#### Scenario: Dispute resolved - delivery confirmed
- **WHEN** dispute resolved in favor of seller/customer
- **AND** delivery confirmed
- **THEN** system SHALL release payment to supplier
- **AND** update status to delivery_confirmed

#### Scenario: Dispute resolved - refund
- **WHEN** dispute resolved in favor of buyer
- **THEN** system SHALL initiate full refund to buyer
- **AND** deduct from supplier if already paid
- **AND** update order status to refunded

### Requirement: Price snapshot at order time
The system SHALL snapshot all prices at order creation to prevent disputes.

#### Scenario: Order created with price snapshot
- **WHEN** order is created
- **THEN** system SHALL store:
  - supplier_price_at_order
  - seller_price_at_order
  - shipping_cost
  - platform_fee (if applicable)
- **AND** these prices are final for this order

#### Scenario: Supplier price changes after order
- **WHEN** supplier updates product price AFTER order created
- **THEN** system SHALL NOT affect existing order prices
- **AND** only new orders get new prices

### Requirement: Order items with supplier groups
The system SHALL track order items by supplier for payment processing.

#### Scenario: Order item with price snapshot
- **WHEN** order item is created
- **THEN** system SHALL store:
  - variant_id
  - quantity
  - supplier_price (at order time)
  - seller_price (at order time)
  - profit (seller_price - supplier_price)
  - supplier_shop_id
