## ADDED Requirements

### Requirement: Category prediction during product import
The system SHALL use Basalam Category Detection API to predict category when supplier imports product.

#### Scenario: Predict category for new product
- **WHEN** supplier imports a new product via Basalam shop sync
- **THEN** system SHALL call categorydetection.basalam.com API with product title and description
- **AND** receive predicted category_id with confidence score
- **AND** store category_status as "predicted"
- **AND** link product to category in catalog_categories

#### Scenario: Category detection API fails
- **WHEN** categorydetection.basalam.com API returns error or timeout
- **THEN** system SHALL set category_status as "unknown"
- **AND** flag product for manual category selection
- **AND** log integration error for retry

#### Scenario: Product has multiple detected categories
- **WHEN** Basalam returns multiple category predictions
- **THEN** system SHALL store primary category (highest confidence)
- **AND** store alternative categories as candidates
- **AND** allow supplier to select from candidates

### Requirement: Category margin validation (Franchise Rules)
The system SHALL enforce minimum margin requirements based on Basalam category franchise rules.

#### Scenario: Validate margin against category franchise
- **WHEN** seller attempts to add product to catalog
- **AND** product has confirmed category with franchise_percent
- **THEN** system SHALL calculate: minimum_allowed_margin = category.franchise_percent
- **AND** if seller_margin < minimum_allowed_margin, reject with error

#### Scenario: Margin below category franchise
- **WHEN** seller sets margin at 15%
- **AND** product category requires minimum 25% franchise
- **THEN** system SHALL reject the listing
- **AND** return error: "حداقل حاشیه سود برای این دسته‌بندی ۲۵٪ می‌باشد"
- **AND** suggest margin equal to franchise_percent

#### Scenario: Category franchise not yet loaded
- **WHEN** product category is "predicted"
- **AND** franchise_percent is not available
- **THEN** system SHALL allow listing with warning
- **AND** store warning: "دسته‌بندی تایید نشده - ممکن است حاشیه سود تغییر کند"

### Requirement: Category confirmation workflow
The system SHALL manage category status lifecycle (predicted → confirmed → manual).

#### Scenario: Supplier confirms category
- **WHEN** supplier manually confirms product category
- **THEN** system SHALL update category_status to "confirmed"
- **AND** lock franchise validation to confirmed category
- **AND** trigger recalculation if margin was previously allowed

#### Scenario: Supplier changes confirmed category
- **WHEN** supplier changes category from A to B
- **AND** category A was confirmed
- **THEN** system SHALL update category_status to "manual"
- **AND** validate new category franchise rules
- **AND** notify seller if margin becomes invalid

#### Scenario: System detects category change from Basalam
- **WHEN** Basalam webhook indicates category changed
- **AND** previous category was "confirmed"
- **THEN** system SHALL update category_status to "predicted"
- **AND** recalculate seller margins against new category
- **AND** notify affected sellers

### Requirement: Category sync from Basalam API
The system SHALL synchronize categories from Basalam including hierarchy and franchise rules.

#### Scenario: Full category sync
- **WHEN** system triggers category sync job
- **THEN** system SHALL fetch all categories from Basalam API
- **AND** store category_id, name, parent_id, franchise_percent
- **AND** build category hierarchy (parent/child relationships)
- **AND** update existing category metadata

#### Scenario: Category has franchise rule
- **WHEN** Basalam category has minimum_margin requirement
- **THEN** system SHALL store franchise_percent in categories table
- **AND** use for margin validation in pricing engine
- **AND** display in seller dashboard category info

#### Scenario: Category hierarchy sync
- **WHEN** syncing categories from Basalam
- **THEN** system SHALL build tree structure using parent_id
- **AND** support category filtering by parent
- **AND** inherit franchise rules from parent if not set

#### Scenario: New category added in Basalam
- **WHEN** Basalam adds new category
- **AND** sync job detects new category_id
- **THEN** system SHALL create new category record
- **AND** integrate into existing hierarchy
- **AND** log for monitoring

### Requirement: Forbidden category detection
The system SHALL detect and block products in forbidden categories per Basalam rules.

#### Scenario: Product in forbidden category
- **WHEN** product category is in forbidden_categories list
- **THEN** system SHALL set product status to "rejected"
- **AND** set rejection_reason to "forbidden_category"
- **AND** notify supplier: "این محصول در دسته‌بندی غیرمجاز قرار دارد"

#### Scenario: Category becomes forbidden after listing
- **WHEN** Basalam marks category as forbidden
- **AND** product is already listed
- **THEN** system SHALL disable product immediately
- **AND** notify all sellers with this product
- **AND** set product status to "archived"

#### Scenario: Manual override of forbidden category
- **WHEN** admin manually approves product in forbidden category
- **THEN** system SHALL log admin_action with admin_id
- **AND** require additional approval reason
- **AND** flag for compliance review

### Requirement: Category status tracking
The system SHALL track category lifecycle states for audit and validation.

#### Scenario: Category status types
- **WHEN** product category is processed
- **THEN** system SHALL support statuses:
  - **predicted**: from Basalam API detection
  - **confirmed**: supplier manually confirmed
  - **manual**: supplier manually selected
  - **rejected**: forbidden or invalid category

#### Scenario: Category status history
- **WHEN** category_status changes
- **THEN** system SHALL create category_status_history record
- **AND** store old_status, new_status, changed_by, changed_at, reason

### Requirement: Category filtering and search
The system SHALL support category-based filtering for seller product selection.

#### Scenario: Filter products by category
- **WHEN** seller browses supplier catalog
- **THEN** system SHALL allow filtering by category_id
- **AND** support parent category to include all children
- **AND** show product count per category

#### Scenario: Category breadcrumb navigation
- **WHEN** displaying product category
- **THEN** system SHALL show full path: Parent > Child > Sub-child
- **AND** allow navigation to any level

### Requirement: Category change notification
The system SHALL notify relevant parties when category status changes.

#### Scenario: Category predicted to confirmed
- **WHEN** category changes from predicted to confirmed
- **THEN** system SHALL notify seller if margin validation affected
- **AND** provide recalculation summary

#### Scenario: Category franchise changed
- **WHEN** Basalam updates franchise_percent for category
- **THEN** system SHALL trigger margin revalidation
- **AND** notify sellers with invalid margins
- **AND** provide grace period before enforcement

## MODIFIED Requirements

### Requirement: Integration with Basalam Category Detection
The system SHALL integrate with categorydetection.basalam.com API for automatic category prediction.

#### Scenario: Call category detection API
- **WHEN** importing product from Basalam
- **THEN** system SHALL call: POST categorydetection.basalam.com/detect
- **WITH** payload: { "title": "...", "description": "...", "keywords": [...] }
- **AND** handle rate limiting with exponential backoff

#### Scenario: Handle API response
- **WHEN** category detection returns success
- **THEN** system SHALL parse response for category_id, confidence
- **AND** store prediction with timestamp
- **AND** continue with product import flow

#### Scenario: API authentication
- **WHEN** calling Basalam category API
- **THEN** system SHALL use vendor access token
- **AND** refresh token if expired
- **AND** log authentication failures

### Requirement: Category hierarchy in product validation
The system SHALL use category hierarchy for franchise validation.

#### Scenario: Validate against parent category franchise
- **WHEN** category has no franchise_percent
- **AND** has parent category
- **THEN** system SHALL inherit franchise from nearest ancestor
- **AND** use parent franchise for validation

#### Scenario: Child category overrides parent
- **WHEN** child category has explicit franchise_percent
- **AND** parent has different franchise
- **THEN** system SHALL use child's franchise_percent
- **AND** NOT inherit from parent
