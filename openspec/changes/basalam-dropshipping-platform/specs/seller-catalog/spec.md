## ADDED Requirements

### Requirement: Seller can browse supplier catalog
The system SHALL allow sellers to browse and filter products from connected suppliers.

#### Scenario: Browse all products
- **WHEN** seller visits catalog page
- **THEN** system SHALL show paginated list of available products
- **AND** include product image, title, supplier, price range

#### Scenario: Filter by supplier
- **WHEN** seller filters by specific supplier
- **THEN** system SHALL show only products from that supplier

#### Scenario: Filter by category
- **WHEN** seller filters by category
- **THEN** system SHALL show products in that category
- **AND** include subcategories

#### Scenario: Search products
- **WHEN** seller searches by keyword
- **THEN** system SHALL match title and description
- **AND** rank results by relevance

### Requirement: Seller can add product to store
The system SHALL allow sellers to add products from catalog to their store.

#### Scenario: Add single product
- **WHEN** seller clicks "Add to Store" on product
- **THEN** system SHALL create seller_product record
- **AND** copy initial data from supplier_product
- **AND** apply seller's margin

#### Scenario: Add product with variants
- **WHEN** seller adds product with variants
- **THEN** system SHALL create seller_variant for each
- **AND** seller can enable/disable specific variants

#### Scenario: Add same product twice
- **WHEN** seller attempts to add already-added product
- **THEN** system SHALL show error "Product already in store"

### Requirement: Seller can override product details
The system SHALL allow sellers to override title, description, and images.

#### Scenario: Override title
- **WHEN** seller edits product title
- **THEN** system SHALL store override value
- **AND** display override on seller store
- **AND** still sync price/inventory from supplier

#### Scenario: Override image
- **WHEN** seller uploads custom image
- **THEN** system SHALL store custom image
- **AND** display custom image instead of supplier image

#### Scenario: Supplier updates overridden product
- **WHEN** supplier updates product that seller has overridden
- **THEN** system SHALL keep seller overrides
- **AND** sync non-overridden fields

### Requirement: Seller can disconnect product
The system SHALL allow sellers to stop selling a product.

#### Scenario: Seller removes product
- **WHEN** seller removes product from store
- **THEN** system SHALL disable seller_product
- **AND** release any inventory reservations
- **AND** keep order history

### Requirement: Seller can filter by availability
The system SHALL allow sellers to see only in-stock products.

#### Scenario: Filter in-stock only
- **WHEN** seller enables "In Stock Only" filter
- **THEN** system SHALL hide out-of-stock products
