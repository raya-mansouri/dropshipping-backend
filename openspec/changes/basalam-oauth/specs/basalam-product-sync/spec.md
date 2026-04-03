## ADDED Requirements

### Requirement: Fetch products with page-based pagination
The system SHALL fetch products from `GET https://openapi.basalam.com/v1/vendors/{vendor_id}/products` using page-based pagination (`page`, `per_page`). The response contains `{data: [...], total_count, result_count, total_page, page, per_page}`. The system SHALL paginate through all pages until `page >= total_page`.

#### Scenario: First page fetch
- **WHEN** a product sync is triggered for an integration with `vendor_id=12345`
- **THEN** the system calls `GET https://openapi.basalam.com/v1/vendors/12345/products?page=1&per_page=50` with `Authorization: Bearer {access_token}`
- **AND** receives up to 50 products in `data` array with `total_page` count

#### Scenario: Paginate through all pages
- **WHEN** `total_page` from response is greater than current page
- **THEN** the system increments `page` and fetches the next page
- **AND** continues until all products are fetched (`page >= total_page`)

#### Scenario: Empty product list
- **WHEN** the vendor has no products (`data` is empty)
- **THEN** sync completes with `created_count=0, updated_count=0`

### Requirement: Map Basalam product to SupplierProduct
The system SHALL map each Basalam product response to the internal `SupplierProduct` model. The real Basalam product shape is:
- `id` → `external_product_id` (string)
- `title` → `title`
- `description` → `description`
- `price` → stored in variant's `cost_price`
- `photo` → parsed for `ProductMedia` (`.original`, `.id`, dimensions)
- `status.value` → mapped to internal status (`2976` = "active")
- `inventory` → variant `inventory`
- `is_wholesale` → stored in `raw_payload`

#### Scenario: Map a simple product without variants
- **WHEN** Basalam returns a product with no `variants` array
- **THEN** the system creates one `SupplierProduct` with `has_variants=False`
- **AND** creates one `ProductVariant` + `SupplierVariant` using the product-level `price` and `inventory`

#### Scenario: Map a product with variants
- **WHEN** Basalam returns a product with a `variants` array
- **THEN** the system creates `SupplierProduct` with `has_variants=True`
- **AND** creates a `ProductVariant` + `SupplierVariant` for each variant with variant-level pricing and inventory

### Requirement: Bulk upsert products with conflict resolution
The system SHALL use PostgreSQL `INSERT ... ON CONFLICT (shop_id, external_product_id) DO UPDATE` for bulk upsert of products and variants. The conflict key for products is `(shop_id, external_product_id)` and for variants is `(supplier_product_id, external_variant_id)`.

#### Scenario: New product inserted
- **WHEN** a product with `external_product_id` not already in DB for this shop is synced
- **THEN** a new `SupplierProduct` record is created with all mapped fields

#### Scenario: Existing product updated
- **WHEN** a product with `external_product_id` already exists for this shop
- **THEN** the existing record is updated with new `title`, `description`, `status`, `raw_payload`, `last_synced_at`

#### Scenario: Batch upsert of 100 products
- **WHEN** 100 products are fetched in a single page
- **THEN** the system processes them in a single bulk upsert operation
- **AND** returns accurate `created_count` and `updated_count`

### Requirement: Track sync state per integration
The system SHALL create a `SyncState` model with fields: `integration_id` (UUID FK), `entity_type` (string: "product"/"inventory"/"order"), `status` (idle/syncing/error), `last_sync_timestamp`, `cursor_token` (nullable), `total_synced`, `created_count`, `updated_count`, `failed_count`, `last_error`, `sync_mode` (full/delta). The system SHALL update sync state after each sync operation.

#### Scenario: First sync creates SyncState
- **WHEN** a product sync runs for the first time for an integration
- **THEN** a `SyncState` record is created with `status="syncing"`, `sync_mode="full"`

#### Scenario: Sync state updated after completion
- **WHEN** a sync completes successfully
- **THEN** `SyncState.status` is set to `"idle"`, `last_sync_timestamp` is updated, and counts are incremented

### Requirement: Delta sync using last_modified
The system SHALL support delta sync by passing `updated_at_min` query parameter (ISO 8601 timestamp) to the Basalam products endpoint. Only products modified after `SyncState.last_sync_timestamp` SHALL be fetched.

#### Scenario: Delta sync after previous full sync
- **WHEN** a sync is triggered and `SyncState.last_sync_timestamp` exists and `full_sync=False`
- **THEN** the system passes `updated_at_min={last_sync_timestamp}` to the API
- **AND** only fetches products modified since the last sync

#### Scenario: Full sync override
- **WHEN** a sync is triggered with `full_sync=True`
- **THEN** the system ignores `last_sync_timestamp` and fetches all products from page 1

### Requirement: Concurrent batch processing with rate limiting
The system SHALL process product batches concurrently using `asyncio.gather` with a semaphore limiting to `MAX_CONCURRENT_BATCHES=5`. Each batch SHALL respect the Basalam rate limit of 100 requests/minute for the products endpoint.

#### Scenario: Process 200 products in batches
- **WHEN** 200 products are fetched across 4 pages
- **THEN** the system creates batches of `BATCH_SIZE=100`
- **AND** processes up to 5 batches concurrently via `asyncio.gather` with semaphore
- **AND** each batch upsert completes independently
