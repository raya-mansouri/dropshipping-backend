## ADDED Requirements

### Requirement: Product revision status tracking from Basalam
The system SHALL track and synchronize product revision/moderation status from Basalam revision.basalam.com API.

#### Scenario: Initial product import triggers revision check
- **WHEN** supplier product is imported from Basalam for the first time
- **THEN** system SHALL call revision.basalam.com API to get initial revision_status
- **AND** store revision_status in supplier_product table (fields: revision_status, revision_id, revision_note, revision_updated_at)
- **AND** set local status based on Basalam response

#### Scenario: Product edit triggers new revision
- **WHEN** supplier edits a product on Basalam (title, description, price, images, variants)
- **THEN** Basalam creates new revision and sets product status to "pending_review"
- **AND** system SHALL receive webhook event product.revision.created
- **AND** update supplier_product.revision_status to "pending_review"
- **AND** store revision_id for tracking
- **AND** set supplier_product.status to "pending_review"
- **AND** disable all linked seller_products

#### Scenario: Poll revision status periodically
- **WHEN** product has revision_status = "pending_review"
- **THEN** system SHALL poll revision.basalam.com API every 5 minutes
- **AND** check if revision has been approved or rejected
- **AND** update status accordingly when change detected

### Requirement: Product pending review handling
The system SHALL properly handle products that are in pending review (moderation) status.

#### Scenario: Product enters pending review
- **WHEN** Basalam sets product to pending_review status
- **THEN** system SHALL update supplier_product.revision_status to "pending_review"
- **AND** set supplier_product.status to "pending_moderation"
- **AND** mark all seller_products.status as "pending_moderation"
- **AND** set seller_product inventory to 0 (prevent sales during review)
- **AND** create audit_log entry for status change
- **AND** trigger notification to supplier

#### Scenario: Product remains pending beyond threshold
- **WHEN** product pending_review exceeds 24 hours
- **THEN** system SHALL log warning for monitoring
- **AND** increment pending_moderation_days counter
- **AND** notify platform admin via internal notification

#### Scenario: Seller views pending product
- **WHEN** seller tries to view product with pending_review status
- **THEN** system SHALL allow read access
- **AND** display message: "این محصول در حال بررسی توسط تیم مدیریت می‌باشد"
- **AND** disable "add to store" action
- **AND** show expected review date if available

### Requirement: Product approved after revision
The system SHALL handle product approval when Basalam accepts the revision.

#### Scenario: Product approved via Basalam
- **WHEN** Basalam approves product revision (revision_status = "approved")
- **THEN** system SHALL receive webhook event product.revision.approved
- **AND** update supplier_product.revision_status to "approved"
- **AND** update supplier_product.status to "active"
- **AND** restore all seller_products.status to "active"
- **AND** restore seller_product inventory from latest data
- **AND** create notification for supplier: "محصول شما تایید شد"
- **AND** create notification for affected sellers: "محصول تامین‌کننده مجدداً فعال شد"
- **AND** create audit_log entry

#### Scenario: Product approved with conditions
- **WHEN** Basalam approves product but with revision_notes (warnings)
- **THEN** system SHALL store revision_notes in supplier_product
- **AND** notify supplier of approval with warnings
- **AND** display warnings in supplier dashboard

### Requirement: Product rejected with reason
The system SHALL handle product rejection with detailed reason from Basalam.

#### Scenario: Product rejected via Basalam
- **WHEN** Basalam rejects product (revision_status = "rejected")
- **THEN** system SHALL receive webhook event product.revision.rejected
- **AND** update supplier_product.revision_status to "rejected"
- **AND** update supplier_product.status to "rejected"
- **AND** store rejection_reason in basalam_validation_error table
- **AND** store revision_notes with detailed rejection explanation
- **AND** disable all seller_products linked to this supplier_product
- **AND** set seller_product status to "supplier_rejected"
- **AND** set seller_product inventory to 0
- **AND** create notification for supplier with rejection reason

#### Scenario: Rejection reason categories
- **WHEN** Basalam provides rejection reason
- **THEN** system SHALL parse and categorize rejection:
  - Category: "forbidden_product" - محصول غیرمجاز
  - Category: "invalid_images" - تصاویر نامعتبر
  - Category: "incorrect_category" - دسته‌بندی نادرست
  - Category: "price_issue" - مشکل قیمت
  - Category: "description_issue" - مشکل در توضیحات
  - Category: "trademark_issue" - نقض علائم تجاری
- **AND** store rejection_category for filtering

#### Scenario: Supplier modifies rejected product
- **WHEN** supplier edits rejected product on Basalam
- **THEN** Basalam creates new revision (new revision_id)
- **AND** system SHALL treat as new pending_review
- **AND** clear previous rejection_reason
- **AND** start new approval workflow

### Requirement: Product returned for edit (needs_revision)
The system SHALL handle Basalam returning product for supplier edits.

#### Scenario: Product needs revision
- **WHEN** Basalam sets product status to "needs_revision"
- **THEN** system SHALL receive webhook event product.revision.needs_revision
- **AND** update supplier_product.revision_status to "needs_revision"
- **AND** store revision_notes with required changes
- **AND** update supplier_product.status to "needs_revision"
- **AND** disable seller_products
- **AND** create notification for supplier with revision requirements

#### Scenario: Supplier views revision requirements
- **WHEN** supplier views product with needs_revision status
- **THEN** system SHALL display revision_notes from Basalam
- **AND** show required changes in Persian
- **AND** provide link to edit on Basalam panel
- **AND** show revision deadline if provided

### Requirement: Image moderation status sync
The system SHALL handle image-specific moderation from Basalam.

#### Scenario: Image passes Basalam validation
- **WHEN** Basalam validates image successfully
- **THEN** system SHALL receive image.validation.passed webhook
- **AND** update supplier_image.moderation_status to "approved"
- **AND** set supplier_image.is_valid to true
- **AND** proceed with normal image sync

#### Scenario: Image fails watermark validation
- **WHEN** Basalam rejects image due to watermark
- **THEN** system SHALL receive image.validation.failed webhook
- **AND** update supplier_image.moderation_status to "rejected"
- **AND** store rejection_reason: "watermark_detected"
- **AND** store rejection_detail: "Watermark found in image"
- **AND** mark image as invalid
- **AND** notify supplier: "تصویر دارای واترمارک است"

#### Scenario: Image fails illegal content validation
- **WHEN** Basalam rejects image due to illegal content
- **THEN** system SHALL receive image.validation.failed webhook
- **AND** update supplier_image.moderation_status to "rejected"
- **AND** store rejection_reason: "illegal_content"
- **AND** mark image as invalid
- **AND** immediately disable affected seller_products
- **AND** create critical notification for supplier

#### Scenario: Image fails copyright validation
- **WHEN** Basalam rejects image due to copyright violation
- **THEN** system SHALL receive image.validation.failed webhook
- **AND** update supplier_image.moderation_status to "rejected"
- **AND** store rejection_reason: "copyright_violation"
- **AND** notify supplier: "تصویر دارای نقض کپی‌رایت است"
- **AND** disable affected seller_products

#### Scenario: Image pending moderation
- **WHEN** Basalam has not yet validated image
- **THEN** system SHALL set supplier_image.moderation_status to "pending"
- **AND** show placeholder in product display
- **AND** not block product (allow other valid images to show)

#### Scenario: All images rejected
- **WHEN** all images for a product are rejected
- **THEN** system SHALL set product status to "needs_revision"
- **AND** force supplier to upload new images
- **AND** disable all seller_products

### Requirement: Product changes after approval
The system SHALL track and handle changes to previously approved products.

#### Scenario: Approved product edited
- **WHEN** supplier edits already-approved product
- **THEN** Basalam creates new revision automatically
- **AND** system receives product.revision.created event
- **AND** old approved version remains active until new approval
- **AND** seller_products remain active during review (grace period)
- **AND** notification sent to sellers: "محصول تامین‌کننده در حال بازنگری است"

#### Scenario: Edit during grace period
- **WHEN** product is under new revision
- **AND** grace period (24 hours) has not expired
- **THEN** system SHALL allow continued sales
- **AND** track pending changes
- **AND** display "در انتظار تایید" badge

#### Scenario: Grace period expired with pending revision
- **WHEN** revision pending over 24 hours
- **THEN** system SHALL disable seller_products
- **AND** set inventory to 0
- **AND** notify sellers: "محصول در انتظار تایید - فروش موقتاً متوقف شد"

### Requirement: Notification to sellers when product goes to revision
The system SHALL send timely notifications to sellers affected by revision status changes.

#### Scenario: Product enters revision
- **WHEN** product.revision.created webhook received
- **THEN** system SHALL query all seller_products linked to supplier_product
- **AND** create notification for each affected seller:
  - Type: "product_revision_started"
  - Title: "محصول در انتظار بازنگری"
  - Body: "محصول [نام محصول] توسط تامین‌کننده ویرایش شد و در انتظار تایید است"
  - Action: link to product in seller dashboard
- **AND** send via: in-app, email, SMS (based on seller preferences)

#### Scenario: Product rejected
- **WHEN** product.revision.rejected webhook received
- **THEN** system SHALL create notification for each affected seller:
  - Type: "product_rejected"
  - Title: "محصول رد شد"
  - Body: "محصول [نام محصول] توسط مدیریت رد شد. علت: [دلیل]"
  - Action: link to product in seller dashboard

#### Scenario: Product approved after revision
- **WHEN** product.revision.approved webhook received
- **THEN** system SHALL create notification for each affected seller:
  - Type: "product_approved"
  - Title: "محصول مجدداً تایید شد"
  - Body: "محصول [نام محصول] مجدداً فعال شد و آماده فروش است"

### Requirement: Disabling seller products when supplier product is rejected
The system SHALL automatically disable seller products when the source supplier product is rejected.

#### Scenario: Supplier product rejected
- **WHEN** supplier_product.revision_status becomes "rejected"
- **THEN** system SHALL immediately:
  - Set all seller_products.status to "supplier_rejected"
  - Set seller_products.inventory to 0
  - Set seller_products.is_active to false
  - Create product_disable_log entry
  - Trigger seller notifications

#### Scenario: Seller views disabled product
- **WHEN** seller tries to access rejected product
- **THEN** system SHALL show:
  - Status badge: "رد شده"
  - Rejection reason: "این محصول توسط مدیریت رد شده است"
  - Original reason from supplier (if available)
  - Option to remove from store

#### Scenario: Seller manually removes rejected product
- **WHEN** seller removes rejected product from their store
- **THEN** system SHALL mark seller_product.status as "seller_removed"
- **AND** not restore if supplier product later approved
- **AND** require manual re-add if seller wants to sell again

#### Scenario: Supplier product approved after rejection
- **WHEN** rejected supplier_product gets re-approved
- **THEN** system SHALL:
  - Set seller_products.status to "active" (for those not manually removed)
  - Restore inventory from latest data
  - Notify sellers: "محصول مجدداً فعال شد"

### Requirement: Revision status API endpoints
The system SHALL provide API endpoints for querying revision status.

#### Scenario: Get product revision status
- **WHEN** seller calls GET /api/v1/seller/products/{id}/revision-status
- **THEN** system SHALL return:
  - revision_status (pending_review, approved, rejected, needs_revision)
  - revision_note (if any)
  - revision_updated_at
  - rejection_reason (if rejected)
  - rejection_category (if rejected)

#### Scenario: Get supplier revision list
- **WHEN** supplier calls GET /api/v1/supplier/products/revisions
- **THEN** system SHALL return paginated list of products with revision status
- **AND** filter by status (pending, approved, rejected)
- **AND** include revision notes and timestamps

#### Scenario: Webhook event structure from Basalam
- **WHEN** Basalam sends revision webhook
- **THEN** expect payload structure:
  ```json
  {
    "event": "product.revision.created|approved|rejected|needs_revision",
    "product_id": "string",
    "revision_id": "string",
    "status": "pending_review|approved|rejected|needs_revision",
    "revision_note": "string (optional)",
    "rejection_reason": "string (optional)",
    "rejection_category": "string (optional)",
    "timestamp": "ISO8601"
  }
  ```

### Requirement: Database schema for revision tracking
The system SHALL maintain proper database schema for revision tracking.

#### Scenario: Supplier product revision fields
- **WHEN** creating supplier_product table
- **THEN** include columns:
  - revision_status: Enum (active, pending_review, approved, rejected, needs_revision)
  - revision_id: String (nullable, Basalam revision ID)
  - revision_note: Text (nullable)
  - revision_created_at: DateTime
  - revision_updated_at: DateTime
  - rejected_at: DateTime (nullable)
  - approved_at: DateTime (nullable)

#### Scenario: Seller product revision tracking
- **WHEN** creating seller_product table
- **AND** link to supplier_product
- **THEN** include columns:
  - status: Enum (active, pending_moderation, supplier_rejected, seller_removed)
  - revision_status_synced_at: DateTime

#### Scenario: Validation error tracking
- **WHEN** product is rejected
- **THEN** create basalam_validation_error record:
  - product_id (FK)
  - error_type: "revision_rejection"
  - error_category: Enum (forbidden_product, invalid_images, incorrect_category, etc.)
  - error_message: Text
  - basalam_error_code: String
  - created_at: DateTime
