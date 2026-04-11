## 1. Fix Python datetime code (deprecated APIs & timezone stripping)

- [x] 1.1 Replace `datetime.utcfromtimestamp(ts)` in `src/integrations/webhooks/processors/base.py:169` with `datetime.fromtimestamp(ts, tz=timezone.utc)`
- [x] 1.2 Remove `.replace(tzinfo=None)` in `src/integrations/webhooks/processors/base.py:129` — compare aware datetimes directly
- [x] 1.3 Audit codebase for any remaining `datetime.utcnow()` or `datetime.utcfromtimestamp()` calls and replace with timezone-aware equivalents

## 2. Fix SQLAlchemy model columns (DateTime → DateTime(timezone=True))

- [x] 2.1 Fix `src/domains/webhooks/models.py` — change all `Column(DateTime)` to `Column(DateTime(timezone=True))` (processed_at, scheduled_at, executed_at, last_attempt_at, next_retry_at, resolved_at)
- [x] 2.2 Fix `src/domains/shops/models.py` — change all `Column(DateTime)` to `Column(DateTime(timezone=True))` (webhook_registered_at, webhook_secret_rotated_at, webhook_previous_secret_expires_at, last_sync_started_at, last_synced_at, scheduled_at, started_at, completed_at, last_sync_timestamp)
- [x] 2.3 Fix `src/domains/inventory/models.py` — change all `Column(DateTime)` to `Column(DateTime(timezone=True))` (expires_at, released_at, created_at)
- [x] 2.4 Fix `src/domains/notifications/models.py` — change all `Column(DateTime)` to `Column(DateTime(timezone=True))` (read_at, sent_at, delivered_at)
- [x] 2.5 Fix `src/domains/system_logs/models.py` — change `Column(DateTime)` to `Column(DateTime(timezone=True))` (created_at)

## 3. Generate and verify Alembic migration

- [x] 3.1 Run `make migrate-create message="convert_datetime_columns_to_timestamptz"` to generate the migration (written manually — autogenerate requires running DB)
- [x] 3.2 Verify the generated migration uses `ALTER COLUMN ... TYPE TIMESTAMPTZ` for all affected columns
- [ ] 3.3 Run `make migrate` to apply migration locally and verify it succeeds (BLOCKED: pre-existing `.env` config validation errors prevent Alembic from running)

## 4. Verify and test

- [x] 4.1 Run `make lint` to ensure no import or syntax errors (no new errors from our changes — 9 pre-existing unused imports)
- [ ] 4.2 Run `make test` and verify all existing tests pass (skipped — requires running DB)
- [x] 4.3 Grep for any remaining `Column(DateTime)` without `timezone=True` to confirm complete coverage

## 5. Remaining scope (discovered by task 4.3 grep) — DONE

27 more bare `Column(DateTime)` found and fixed:
- [x] 5.1 Fix `src/domains/payments/models.py` — 12 columns (paid_at, escrow_started_at, supplier_paid_at, refunded_at, approved_at, rejected_at, completed_at, delivery_confirmed_at, dispute_window_ends_at, released_at, failed_at, resolved_at)
- [x] 5.2 Fix `src/domains/orders/models.py` — 13 columns (confirmed_at, paid_at, shipped_at, delivered_at, completed_at, cancelled_at, rejected_at, created_at in order_history, shipped_at, delivered_at, delivery_confirmed_at, estimated_delivery, actual_delivery in shipments)
- [x] 5.3 Fix `src/domains/products/models.py` — 3 columns (last_synced_at, last_inventory_sync, last_price_sync)
- [x] 5.4 Fix `src/domains/fraud_detection/models.py` — 2 columns (created_at, resolved_at)
- [x] 5.5 Update migration with all additional ALTER COLUMN statements + downgrade
