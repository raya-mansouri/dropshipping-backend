## ADDED Requirements

### Requirement: Product sync must be idempotent
The system SHALL process product updates idempotently to prevent duplicate operations.

#### Scenario: Duplicate webhook received
- **WHEN** same product_update webhook received twice
- **THEN** system SHALL only process once
- **AND** system SHALL return success for second request

#### Scenario: Webhook with new product
- **WHEN** webhook received for new product from supplier
- **THEN** system SHALL create new supplier_product record
- **AND** system SHALL import variants, images, inventory

### Requirement: Product sync must handle variants
The system SHALL properly sync products with multiple variants (size, color, etc.).

#### Scenario: Product with variants
- **WHEN** supplier product has multiple variants
- **THEN** system SHALL create variant records for each
- **AND** each variant must have separate price and inventory

#### Scenario: New variant added
- **WHEN** supplier adds new variant to existing product
- **THEN** system SHALL create new variant record
- **AND** notify sellers who have this product

#### Scenario: Variant removed by supplier
- **WHEN** supplier removes variant from product
- **THEN** system SHALL disable the variant
- **AND** notify sellers who had this variant
- **AND** set seller variant inventory to 0

### Requirement: Product sync must handle images
The system SHALL sync and optimize product images from Basalam.

#### Scenario: Product image sync
- **WHEN** product has images in Basalam
- **THEN** system SHALL download images to object storage
- **AND** generate multiple sizes (thumbnail, medium, large)
- **AND** serve via CDN

#### Scenario: Image changed
- **WHEN** supplier changes product image
- **THEN** system SHALL download new image
- **AND** update CDN links
- **AND** invalidate cache

#### Scenario: Image deleted
- **WHEN** supplier deletes product image
- **THEN** system SHALL mark image as deleted
- **AND** update seller product images

### Requirement: Product sync must handle archived products
The system SHALL properly handle products that are archived in Basalam.

#### Scenario: Product archived
- **WHEN** Basalam marks product as archived
- **THEN** system SHALL set supplier_product status to archived
- **AND** disable all seller products linked to this
- **AND** set inventory to 0
- **AND** notify affected sellers

### Requirement: Full product import
The system SHALL support initial full import of all supplier products.

#### Scenario: Initial import triggered
- **WHEN** supplier connects shop for first time
- **THEN** system SHALL fetch all products via paginated API
- **AND** import all variants, images, inventory
- **AND** report progress to supplier

### Requirement: Product sync error handling
The system SHALL handle API errors gracefully with retry logic.

#### Scenario: API rate limit exceeded
- **WHEN** Basalam API returns 429
- **THEN** system SHALL wait with exponential backoff
- **AND** retry request

#### Scenario: API timeout
- **WHEN** Basalam API times out
- **THEN** system SHALL retry up to 3 times
- **AND** move to dead letter queue after max retries

## MODIFIED Requirements

### Requirement: Basalam revision/moderation status
The system SHALL sync product revision status from Basalam.

#### Scenario: Product pending review
- **WHEN** Basalam sets product to pending_review status
- **THEN** system SHALL set supplier_product status to pending_review
- **AND** disable all seller products for this item
- **AND** notify affected sellers

#### Scenario: Product approved after review
- **WHEN** Basalam approves product (revision accepted)
- **THEN** system SHALL set supplier_product status to active
- **AND** re-enable seller products
- **AND** notify sellers

#### Scenario: Product rejected after review
- **WHEN** Basalam rejects product (revision rejected)
- **THEN** system SHALL set supplier_product status to forbidden
- **AND** store rejection reason in basalam_validation_error
- **AND** disable all seller products
- **AND** notify supplier with rejection reason

#### Scenario: Product returned for edit
- **WHEN** Basalam returns product for edit (needs_revision)
- **THEN** system SHALL set supplier_product status to needs_revision
- **AND** store revision notes
- **AND** notify supplier to fix product

### Requirement: Category detection
The system SHALL use Basalam category detection API.

#### Scenario: Category detected on import
- **WHEN** product is imported from Basalam
- **THEN** system SHALL call Basalam category detection API
- **AND** store detected category
- **AND** validate against franchise rules

#### Scenario: Category prediction received
- **WHEN** Basalam returns category prediction
- **THEN** system SHALL mark category_status as 'predicted'
- **AND** allow supplier to confirm or change
- **AND** enforce minimum margin based on category

### Requirement: Image moderation from Basalam
The system SHALL handle Basalam image validation.

#### Scenario: Image passes Basalam validation
- **WHEN** Basalam validates image successfully
- **THEN** system SHALL mark image as validated
- **AND** proceed with sync

#### Scenario: Image fails Basalam validation
- **WHEN** Basalam rejects image (watermark, illegal content)
- **THEN** system SHALL mark image as rejected
- **AND** store rejection reason
- **AND** notify supplier
- **AND** disable affected seller products
