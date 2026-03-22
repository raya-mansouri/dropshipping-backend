## ADDED Requirements

### Requirement: Supplier can connect Basalam shop via OAuth
The system SHALL allow suppliers to connect their Basalam shop using OAuth 2.0 authentication flow.

#### Scenario: Successful OAuth connection
- **WHEN** supplier initiates OAuth connection with valid Basalam credentials
- **THEN** system stores access_token and refresh_token securely
- **AND** system creates supplier record with platform_shop_id
- **AND** system associates connection with supplier user account

#### Scenario: OAuth token expiration
- **WHEN** access_token expires during API call
- **THEN** system SHALL automatically refresh token using refresh_token
- **AND** system SHALL update stored tokens
- **AND** retry the original request

#### Scenario: OAuth token refresh failure
- **WHEN** refresh_token is invalid or expired
- **THEN** system SHALL notify supplier to reconnect
- **AND** system SHALL mark connection as disconnected

### Requirement: Supplier can upload products manually
The system SHALL allow suppliers to create products manually without Basalam connection.

#### Scenario: Manual product creation
- **WHEN** supplier fills product form with title, description, price, inventory
- **THEN** system SHALL create product with manual source type
- **AND** supplier can update product at any time

#### Scenario: Manual product with variants
- **WHEN** supplier creates product with multiple variants (size, color)
- **THEN** system SHALL create variant records linked to product
- **AND** each variant can have independent price and inventory

### Requirement: Supplier can import products via CSV/Sheet
The system SHALL allow suppliers to bulk import products from CSV or Google Sheet.

#### Scenario: CSV upload
- **WHEN** supplier uploads CSV file with product data
- **THEN** system SHALL parse CSV and validate columns
- **AND** system SHALL create products for valid rows
- **AND** system SHALL report errors for invalid rows

#### Scenario: Google Sheet import
- **WHEN** supplier provides Sheet URL and range
- **THEN** system SHALL fetch data from Google Sheets API
- **AND** system SHALL create products similar to CSV import

### Requirement: Supplier can manage multiple shops
The system SHALL allow a supplier to manage multiple Basalam shops.

#### Scenario: Adding second shop
- **WHEN** supplier connects additional Basalam shop
- **THEN** system SHALL create new shop record linked to same supplier
- **AND** products from both shops appear in supplier dashboard

### Requirement: Shop uniqueness constraint
Each shop MUST be unique by platform_type + platform_shop_id combination.

#### Scenario: Duplicate shop detection
- **WHEN** supplier attempts to connect shop already connected by another supplier
- **THEN** system SHALL reject connection
- **AND** system SHALL show error message

### Requirement: Supplier can disconnect shop
The system SHALL allow suppliers to disconnect their Basalam shop.

#### Scenario: Successful disconnect
- **WHEN** supplier requests to disconnect shop
- **THEN** system SHALL mark shop as disconnected
- **AND** system SHALL keep historical data
- **AND** active products shall be disabled

## MODIFIED Requirements

### Requirement: Supplier can connect Basalam shop via OAuth

#### Scenario: Connection with different Basalam API services
- **WHEN** supplier connects using Basalam OAuth
- **THEN** system SHALL also configure webhooks for:
  - order.created / order.updated
  - product.updated
  - inventory.updated
  - payment.completed
- **AND** system SHALL register webhook endpoint with Basalam

#### Scenario: Shop role is exclusively supplier OR seller
- **WHEN** creating a new shop
- **THEN** shop_role MUST be either 'supplier' OR 'seller'
- **AND** shop_role CANNOT be 'both'
- **AND** each shop can only have one role
