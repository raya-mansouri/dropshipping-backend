## ADDED Requirements

### Requirement: Forbidden category detection
The system SHALL detect and flag products in forbidden categories.

#### Scenario: Product in forbidden category
- **WHEN** product category is in forbidden list
- **THEN** system SHALL set product status to rejected
- **AND** notify supplier
- **AND** prevent sellers from adding

### Requirement: Keyword-based content filtering
The system SHALL scan product titles and descriptions for prohibited keywords.

#### Scenario: Forbidden keyword detected
- **WHEN** product title/description contains prohibited keywords
- **THEN** system SHALL flag product for review
- **AND** notify supplier
- **AND** require manual approval

### Requirement: Basalam moderation status sync
The system SHALL sync product moderation status from Basalam.

#### Scenario: Product pending review
- **WHEN** Basalam sets product to pending_review
- **THEN** system SHALL disable seller products
- **AND** notify sellers

#### Scenario: Product approved
- **WHEN** Basalam approves previously pending product
- **THEN** system SHALL re-enable seller products
- **AND** notify sellers

### Requirement: Image moderation
The system SHALL validate product images against Basalam policies.

#### Scenario: Image rejected by Basalam
- **WHEN** Basalam rejects product image
- **THEN** system SHALL mark image as rejected
- **AND** notify supplier
- **AND** disable affected seller products

### Requirement: Manual override for forbidden products
The system SHALL allow admin to override forbidden product decisions.

#### Scenario: Admin approves forbidden product
- **WHEN** admin manually approves flagged product
- **THEN** system SHALL override rejection
- **AND** log admin action
- **AND** enable for sellers

### Requirement: Forbidden product list management
The system SHALL maintain and update forbidden category/keyword lists.

#### Scenario: New forbidden category added
- **WHEN** admin adds category to forbidden list
- **THEN** system SHALL apply to new imports
- **AND** scan existing products
