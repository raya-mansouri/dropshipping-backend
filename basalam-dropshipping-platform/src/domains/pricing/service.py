"""
Pricing Service
===============
Business logic for pricing calculations and validation

Handles:
- Price calculation: supplier_price + margin = seller_price
- Price validation against category franchise rules
- Price snapshot at order time
- Price history tracking
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from .models import PriceHistory
from ..products.models import Category
from .repository import PricingRepository


@dataclass
class PriceSnapshot:
    """Price snapshot at order time"""

    variant_id: UUID
    supplier_price: Decimal
    seller_price: Decimal
    margin_percent: Decimal
    category_franchise_percent: Decimal
    is_valid: bool
    validation_errors: List[str]


@dataclass
class PriceCalculation:
    """Price calculation result"""

    supplier_price: Decimal
    margin_percent: Decimal
    seller_price: Decimal
    profit: Decimal
    category_franchise_percent: Decimal
    meets_franchise_requirement: bool


class PricingService:
    """
    Service for pricing calculations and validation.

    Handles:
    - Price calculation from supplier price + margin
    - Validation against category franchise rules
    - Price snapshot creation
    - Price history tracking
    """

    def __init__(self, session: AsyncSession, event_publisher=None):
        self.session = session
        self.event_publisher = event_publisher
        self.repo = PricingRepository(session)

    async def calculate_price(
        self,
        supplier_price: Decimal,
        margin_percent: Decimal,
        category_id: Optional[UUID] = None,
    ) -> PriceCalculation:
        """
        Calculate seller price from supplier price and margin.

        Formula: seller_price = supplier_price * (1 + margin_percent / 100)

        Args:
            supplier_price: Cost price from supplier
            margin_percent: Margin percentage to apply
            category_id: Optional category for franchise validation

        Returns:
            PriceCalculation with calculated prices and validation
        """
        category_franchise_percent = Decimal("0")

        if category_id:
            from ..products.models import Category

            result = await self.session.execute(
                Category.__table__.select().where(Category.id == category_id)
            )
            category_row = result.fetchone()
            if category_row:
                category_franchise_percent = Decimal(
                    str(category_row.franchise_percent or 0)
                )

        seller_price = supplier_price * (Decimal("1") + margin_percent / Decimal("100"))
        seller_price = seller_price.quantize(Decimal("0.01"))

        profit = seller_price - supplier_price

        effective_margin = (
            (profit / supplier_price * Decimal("100"))
            if supplier_price > 0
            else Decimal("0")
        )
        meets_franchise = effective_margin >= category_franchise_percent

        return PriceCalculation(
            supplier_price=supplier_price,
            margin_percent=margin_percent,
            seller_price=seller_price,
            profit=profit,
            category_franchise_percent=category_franchise_percent,
            meets_franchise_requirement=meets_franchise,
        )

    async def validate_price(
        self,
        seller_price: Decimal,
        supplier_price: Decimal,
        category_id: UUID,
    ) -> PriceSnapshot:
        """
        Validate price against category franchise rules.

        Args:
            seller_price: The price to validate
            supplier_price: Supplier cost price
            category_id: Category UUID for franchise rules

        Returns:
            PriceSnapshot with validation results
        """
        from ..products.models import Category

        result = await self.session.execute(
            Category.__table__.select().where(Category.id == category_id)
        )
        category_row = result.fetchone()

        if not category_row:
            return PriceSnapshot(
                variant_id=category_id,
                supplier_price=supplier_price,
                seller_price=seller_price,
                margin_percent=Decimal("0"),
                category_franchise_percent=Decimal("0"),
                is_valid=False,
                validation_errors=["Category not found"],
            )

        category_franchise_percent = Decimal(str(category_row.franchise_percent or 0))

        if category_row.is_forbidden:
            return PriceSnapshot(
                variant_id=category_id,
                supplier_price=supplier_price,
                seller_price=seller_price,
                margin_percent=Decimal("0"),
                category_franchise_percent=category_franchise_percent,
                is_valid=False,
                validation_errors=["Category is forbidden"],
            )

        errors = []

        if seller_price < supplier_price:
            errors.append("Seller price cannot be less than supplier price")

        if category_franchise_percent > 0:
            calculated_margin = (
                ((seller_price - supplier_price) / supplier_price * Decimal("100"))
                if supplier_price > 0
                else Decimal("0")
            )
            if calculated_margin < category_franchise_percent:
                errors.append(
                    f"Margin {calculated_margin:.2f}% does not meet "
                    f"franchise requirement of {category_franchise_percent}%"
                )

        margin_percent = (
            ((seller_price - supplier_price) / supplier_price * Decimal("100"))
            if supplier_price > 0
            else Decimal("0")
        )

        return PriceSnapshot(
            variant_id=category_id,
            supplier_price=supplier_price,
            seller_price=seller_price,
            margin_percent=margin_percent,
            category_franchise_percent=category_franchise_percent,
            is_valid=len(errors) == 0,
            validation_errors=errors,
        )

    async def create_price_snapshot(
        self,
        variant_id: UUID,
        supplier_price: Decimal,
        seller_price: Decimal,
        listing_id: Optional[UUID] = None,
    ) -> PriceHistory:
        """
        Create a price snapshot at order time.

        Args:
            variant_id: Supplier variant UUID
            supplier_price: Supplier cost price at snapshot time
            seller_price: Seller price at snapshot time
            listing_id: Optional seller listing UUID

        Returns:
            Created PriceHistory record
        """
        margin_percent = (
            ((seller_price - supplier_price) / supplier_price * Decimal("100"))
            if supplier_price > 0
            else Decimal("0")
        )

        price_history = await self.repo.create({
            "id": uuid4(),
            "variant_id": variant_id,
            "listing_id": listing_id,
            "old_price": seller_price,
            "new_price": seller_price,
            "old_supplier_price": supplier_price,
            "new_supplier_price": supplier_price,
            "margin_percent": margin_percent,
            "margin_changed": "unchanged",
            "change_reason": "order_snapshot",
            "created_at": datetime.now(timezone.utc),
        })

        return price_history

    async def record_price_change(
        self,
        variant_id: UUID,
        old_price: Decimal,
        new_price: Decimal,
        old_supplier_price: Decimal,
        new_supplier_price: Decimal,
        listing_id: Optional[UUID] = None,
        reason: str = "manual",
    ) -> PriceHistory:
        """
        Record a price change in history.

        Args:
            variant_id: Supplier variant UUID
            old_price: Previous seller price
            new_price: New seller price
            old_supplier_price: Previous supplier price
            new_supplier_price: New supplier price
            listing_id: Optional seller listing UUID
            reason: Reason for change (supplier_price_change, margin_change, manual, sync)

        Returns:
            Created PriceHistory record
        """
        old_margin = (
            ((old_price - old_supplier_price) / old_supplier_price * Decimal("100"))
            if old_supplier_price > 0
            else Decimal("0")
        )
        new_margin = (
            ((new_price - new_supplier_price) / new_supplier_price * Decimal("100"))
            if new_supplier_price > 0
            else Decimal("0")
        )

        if new_margin > old_margin:
            margin_changed = "increased"
        elif new_margin < old_margin:
            margin_changed = "decreased"
        else:
            margin_changed = "unchanged"

        price_history = await self.repo.create({
            "id": uuid4(),
            "variant_id": variant_id,
            "listing_id": listing_id,
            "old_price": old_price,
            "new_price": new_price,
            "old_supplier_price": old_supplier_price,
            "new_supplier_price": new_supplier_price,
            "margin_percent": new_margin,
            "margin_changed": margin_changed,
            "change_reason": reason,
            "created_at": datetime.now(timezone.utc),
        })

        return price_history

    async def get_price_history(
        self,
        variant_id: UUID,
        limit: int = 50,
    ) -> List[PriceHistory]:
        """
        Get price history for a variant.

        Args:
            variant_id: Supplier variant UUID
            limit: Maximum number of records to return

        Returns:
            List of PriceHistory records
        """
        return await self.repo.get_by_variant(variant_id, limit=limit)

    async def get_latest_price(
        self,
        variant_id: UUID,
    ) -> Optional[PriceHistory]:
        """
        Get the most recent price for a variant.

        Args:
            variant_id: Supplier variant UUID

        Returns:
            Most recent PriceHistory record or None
        """
        return await self.repo.get_latest(variant_id)


class FranchiseValidator:
    """
    Validator for category franchise rules.

    Ensures prices meet minimum margin requirements per category.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def validate_listing(
        self,
        listing_id: UUID,
    ) -> Dict[str, Any]:
        """
        Validate a seller listing against franchise rules.

        Args:
            listing_id: Seller listing UUID

        Returns:
            Validation result with is_valid and errors
        """
        from ..products.models import SellerListing, SupplierProduct, Category

        result = await self.session.execute(
            SellerListing.__table__.select().where(SellerListing.id == listing_id)
        )
        listing = result.fetchone()

        if not listing:
            return {"is_valid": False, "errors": ["Listing not found"]}

        result = await self.session.execute(
            SupplierProduct.__table__.select()
            .join(Category, Category.id == SupplierProduct.category_id)
            .where(SupplierProduct.id == listing.supplier_product_id)
        )
        product = result.fetchone()

        if not product:
            return {"is_valid": False, "errors": ["Product not found"]}

        errors = []

        if product.category_id:
            result = await self.session.execute(
                Category.__table__.select().where(Category.id == product.category_id)
            )
            category = result.fetchone()

            if category:
                if category.is_forbidden:
                    errors.append("Category is forbidden")

                franchise_percent = category.franchise_percent or 0

                if listing.margin_percent < 0:
                    errors.append("Margin cannot be negative")

                if listing.margin_percent < franchise_percent:
                    errors.append(
                        f"Margin {listing.margin_percent}% does not meet "
                        f"franchise requirement of {franchise_percent}%"
                    )

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "listing_id": listing_id,
        }

    async def get_franchise_requirement(
        self,
        category_id: UUID,
    ) -> Optional[Decimal]:
        """
        Get franchise percentage for a category.

        Args:
            category_id: Category UUID

        Returns:
            Franchise percentage or None if category not found
        """
        result = await self.session.execute(
            Category.__table__.select().where(Category.id == category_id)
        )
        category = result.fetchone()

        if not category:
            return None

        return Decimal(str(category.franchise_percent or 0))
