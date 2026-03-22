## ADDED Requirements

### Requirement: Price calculation chain
The system SHALL calculate final seller price through a defined chain.

#### Scenario: Calculate seller price
- **WHEN** seller adds product to catalog
- **THEN** system SHALL calculate: supplier_price + seller_margin = seller_price
- **AND** store both supplier_price and seller_price

#### Scenario: Supplier price changes
- **WHEN** supplier updates product price
- **THEN** system SHALL recalculate all seller prices
- **AND** notify sellers of price change

### Requirement: Price snapshot at order time
The system SHALL snapshot prices at order creation to protect both parties.

#### Scenario: Order created
- **WHEN** order is created
- **THEN** system SHALL store supplier_price_at_order
- **AND** store seller_price_at_order
- **AND** store shipping_cost
- **AND** store platform_fee (if applicable)

#### Scenario: Price changes during checkout
- **WHEN** supplier changes price while buyer checking out
- **THEN** system SHALL use price at order creation
- **AND** NOT apply new price to existing order

### Requirement: Seller margin management
The system SHALL allow sellers to set and modify margins.

#### Scenario: Seller sets margin
- **WHEN** seller sets margin percentage on product
- **THEN** system SHALL calculate new seller_price
- **AND** validate against minimum price rules

#### Scenario: Negative margin attempt
- **WHEN** seller attempts to set negative margin
- **THEN** system SHALL reject the request
- **AND** return validation error

### Requirement: Minimum price rules
The system SHALL enforce minimum price rules based on category.

#### Scenario: Margin below category minimum
- **WHEN** seller sets margin below category minimum
- **THEN** system SHALL warn seller
- **AND** suggest minimum margin for category

### Requirement: Currency handling
The system SHALL handle currency with proper precision.

#### Scenario: Price rounding
- **WHEN** calculated price has more than 2 decimal places
- **THEN** system SHALL round to nearest Toman (IRR)
- **AND** store exact value

### Requirement: Price history tracking
The system SHALL track all price changes for audit.

#### Scenario: Price changes
- **WHEN** supplier price changes OR seller margin changes
- **THEN** system SHALL create price_history record
- **AND** store old and new values
- **AND** store timestamp and reason

## MODIFIED Requirements

### Requirement: Category franchise validation
The system SHALL enforce minimum margin rules based on Basalam category franchise.

#### Scenario: Category has franchise rule
- **WHEN** product category has minimum franchise_percent in Basalam
- **THEN** system SHALL sync franchise_percent to categories table
- **AND** enforce minimum margin when seller adds product

#### Scenario: High-franchise category
- **WHEN** product category requires 30% margin
- **AND** seller tries to set 20% margin
- **THEN** system SHALL reject with error
- **AND** show "Minimum margin for this category is 30%"

#### Scenario: Category confirmed by supplier
- **WHEN** supplier confirms product category
- **THEN** system SHALL mark category_status as confirmed
- **AND** enforce franchise rules strictly

#### Scenario: Category is predicted
- **WHEN** Basalam returns predicted category
- **THEN** system SHALL allow lower margin temporarily
- **AND** warn seller category may change
- **AND** recalculate if category confirmed differently

### Requirement: Platform fee calculation
The system SHALL calculate platform fee if applicable.

#### Scenario: Platform fee enabled
- **WHEN** order is created AND platform fee is configured
- **THEN** system SHALL calculate: platform_fee = seller_price * fee_percent
- **AND** store in order record
- **AND** deduct from seller payout

#### Scenario: Platform fee disabled
- **WHEN** platform fee is not configured
- **THEN** platform_fee = 0
- **AND** full amount goes to seller
