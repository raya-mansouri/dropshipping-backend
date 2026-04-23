"""add unique constraints for product upsert

Revises: a1b2c3d4e5f6
Create Date: 2026-04-22

Adds unique constraints needed for on_conflict_do_update upserts:
- supplier_products: (shop_id, external_product_id)
- supplier_variants: (supplier_product_id, variant_id)
"""

from alembic import op


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_supplier_products_shop_external",
        "supplier_products",
        ["shop_id", "external_product_id"],
    )
    op.create_unique_constraint(
        "uq_supplier_variants_product_variant",
        "supplier_variants",
        ["supplier_product_id", "variant_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_supplier_variants_product_variant",
        "supplier_variants",
        type_="unique",
    )
    op.drop_constraint(
        "uq_supplier_products_shop_external",
        "supplier_products",
        type_="unique",
    )
