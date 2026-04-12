## MODIFIED Requirements

### Requirement: Correct OAuth scopes
The system SHALL request the following scopes when generating the authorization URL: `vendor.product.read vendor.parcel.read vendor.shipping.read`. The scope separator SHALL be a space character (`+` URL-encoded). These scopes cover product sync, parcel/order tracking, and shipping operations required by the platform.

#### Scenario: Scopes match Basalam API requirements
- **WHEN** the authorization URL is generated
- **THEN** the `scope` parameter contains `vendor.product.read+vendor.parcel.read+vendor.shipping.read`
- **AND** covers product reading, parcel tracking, and shipping operations needed by the integration
