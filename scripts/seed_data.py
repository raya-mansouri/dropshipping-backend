"""
Seed Data Script
================
Populates the database with test data for development.

Run with:
    cd /home/raya/projects/dropshipping-backend && poetry run python scripts/seed_data.py
"""

import asyncio
import sys
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is on sys.path so `src.*` imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bcrypt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_maker, engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash password using bcrypt (same as src/api/v1/auth.py)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def exists(session: AsyncSession, model, **filters) -> bool:
    """Return True if a row matching *filters* already exists."""
    stmt = select(model).filter_by(**filters)
    result = await session.execute(stmt)
    return result.scalars().first() is not None


async def get_one(session: AsyncSession, model, **filters):
    """Return the first matching row or None."""
    stmt = select(model).filter_by(**filters)
    result = await session.execute(stmt)
    return result.scalars().first()


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

async def seed_platforms(session: AsyncSession):
    """Ensure the basalam platform row exists."""
    from src.domains.shops.models import Platform

    platform = await get_one(session, Platform, code="basalam")
    if platform:
        print("  [skip] Platform 'basalam' already exists")
        return platform

    platform = Platform(
        code="basalam",
        name="Basalam",
        platform_type="marketplace",
    )
    session.add(platform)
    await session.flush()
    print("  [add ] Platform 'basalam'")
    return platform


async def seed_users(session: AsyncSession):
    """Create super_admin, supplier, and seller users with accounts."""
    from src.domains.accounts.models import User, Account

    # --- Super Admin ---
    admin = await get_one(session, User, phone="09999999999")
    if not admin:
        admin = User(
            phone="09999999999",
            password_hash=hash_password("Admin123!"),
            full_name="Admin",
            is_active=True,
            is_verified=True,
            role="super_admin",
        )
        session.add(admin)
        await session.flush()
        print("  [add ] User Admin (super_admin)")
    else:
        print("  [skip] User Admin already exists")

    # --- Supplier User ---
    supplier_user = await get_one(session, User, phone="09111111111")
    supplier_account = None
    if not supplier_user:
        supplier_user = User(
            phone="09111111111",
            password_hash=hash_password("Supplier1!"),
            full_name="Supplier One",
            is_active=True,
            is_verified=True,
            role="user",
        )
        session.add(supplier_user)
        await session.flush()

        supplier_account = Account(
            owner_user_id=supplier_user.id,
            account_type="supplier",
            business_name="تامین‌کننده تست",
            status="active",
        )
        session.add(supplier_account)
        await session.flush()
        print("  [add ] User Supplier One + Account")
    else:
        supplier_account = await get_one(session, Account, owner_user_id=supplier_user.id)
        print("  [skip] User Supplier One already exists")

    # --- Seller User ---
    seller_user = await get_one(session, User, phone="09222222222")
    seller_account = None
    if not seller_user:
        seller_user = User(
            phone="09222222222",
            password_hash=hash_password("Seller1!"),
            full_name="Seller One",
            is_active=True,
            is_verified=True,
            role="user",
        )
        session.add(seller_user)
        await session.flush()

        seller_account = Account(
            owner_user_id=seller_user.id,
            account_type="seller",
            business_name="فروشنده تست",
            status="active",
        )
        session.add(seller_account)
        await session.flush()
        print("  [add ] User Seller One + Account")
    else:
        seller_account = await get_one(session, Account, owner_user_id=seller_user.id)
        print("  [skip] User Seller One already exists")

    return admin, supplier_user, supplier_account, seller_user, seller_account


async def seed_shops(session, supplier_account, seller_account):
    """Create supplier and seller shops."""
    from src.domains.shops.models import Shop

    supplier_shop = await get_one(
        session, Shop, account_id=supplier_account.id, shop_role="supplier"
    )
    if not supplier_shop:
        supplier_shop = Shop(
            account_id=supplier_account.id,
            name="غرفه تست باسلام",
            shop_role="supplier",
            status="active",
        )
        session.add(supplier_shop)
        await session.flush()
        print("  [add ] Shop (supplier)")
    else:
        print("  [skip] Shop (supplier) already exists")

    seller_shop = await get_one(
        session, Shop, account_id=seller_account.id, shop_role="seller"
    )
    if not seller_shop:
        seller_shop = Shop(
            account_id=seller_account.id,
            name="فروشگاه تست",
            shop_role="seller",
            status="active",
        )
        session.add(seller_shop)
        await session.flush()
        print("  [add ] Shop (seller)")
    else:
        print("  [skip] Shop (seller) already exists")

    return supplier_shop, seller_shop


async def seed_categories(session):
    """Create 5 product categories (Persian names)."""
    from src.domains.products.models import Category

    NAMES = [
        "پوشاک",         # پوشاک
        "لوازم الکترونیکی",  # لوازم الکترونیکی
        "لوازم خانگی",    # لوازم خانگی
        "زیورآلات",     # زیورآلات
        "لوازم تحریر",     # لوازم تحریر
    ]

    categories = []
    for name in NAMES:
        cat = await get_one(session, Category, name=name)
        if cat:
            print(f"  [skip] Category '{name}' already exists")
        else:
            cat = Category(
                name=name,
                is_active=True,
            )
            session.add(cat)
            await session.flush()
            print(f"  [add ] Category '{name}'")
        categories.append(cat)

    return categories


async def seed_supplier_products(session, supplier_shop, categories):
    """Create 5 supplier products with variants."""
    from src.domains.products.models import (
        SupplierProduct,
        ProductVariant,
        SupplierVariant,
    )

    PRODUCTS = [
        {
            "title": "تی‌شرت نخی مردانه",
            "desc": "تی‌شرت نخی بدون آستین",
            "price": 350000,
            "inventory": 50,
            "sku": "TS-NK-M",
            "attrs": {"color": "سیاه", "size": "M"},
        },
        {
            "title": "کنسول بازی PS5",
            "desc": "پلی‌استیشن 5 نسخه دیجیتال",
            "price": 25000000,
            "inventory": 10,
            "sku": "PS5-DIG",
            "attrs": {"edition": "digital"},
        },
        {
            "title": "جارو برقی سامسونگ",
            "desc": "جارو رباتیک مدل VR05",
            "price": 8900000,
            "inventory": 20,
            "sku": "SM-VR05",
            "attrs": {"color": "سفید"},
        },
        {
            "title": "دستبند نقره",
            "desc": "دستبند نقره اصیل طلایی",
            "price": 1200000,
            "inventory": 100,
            "sku": "SB-SLV",
            "attrs": {"material": "نقره", "weight": "5g"},
        },
        {
            "title": "دفتر یدداشت A5",
            "desc": "دفتر یدداشت فنی کاغذی A5",
            "price": 85000,
            "inventory": 200,
            "sku": "NB-A5",
            "attrs": {"pages": 120, "cover": "سخت"},
        },
    ]

    products = []
    for idx, pdata in enumerate(PRODUCTS):
        product = await get_one(
            session,
            SupplierProduct,
            shop_id=supplier_shop.id,
            title=pdata["title"],
        )
        if product:
            print(f"  [skip] SupplierProduct '{pdata['title']}' already exists")
            products.append(product)
            continue

        product = SupplierProduct(
            shop_id=supplier_shop.id,
            title=pdata["title"],
            description=pdata["desc"],
            category_id=categories[idx].id,
            has_variants=True,
            status="active",
        )
        session.add(product)
        await session.flush()

        variant = ProductVariant(
            product_id=product.id,
            sku=pdata["sku"],
            attributes=pdata["attrs"],
        )
        session.add(variant)
        await session.flush()

        supplier_variant = SupplierVariant(
            supplier_product_id=product.id,
            variant_id=variant.id,
            cost_price=Decimal(pdata["price"]),
            inventory=pdata["inventory"],
            reserved_inventory=0,
            status="active",
        )
        session.add(supplier_variant)
        await session.flush()
        print(f"  [add ] SupplierProduct '{pdata['title']}' + variant")
        products.append(product)

    return products


async def seed_seller_listings(session, seller_shop, supplier_products):
    """Create 3 seller listings from supplier catalog."""
    from src.domains.products.models import SellerListing, SellerVariant, SupplierVariant

    MARGIN = Decimal("20.00")

    listings = []
    for idx, sproduct in enumerate(supplier_products[:3]):
        listing = await get_one(
            session,
            SellerListing,
            shop_id=seller_shop.id,
            supplier_product_id=sproduct.id,
        )
        if listing:
            print(f"  [skip] SellerListing for '{sproduct.title}' already exists")
            listings.append(listing)
            continue

        listing = SellerListing(
            shop_id=seller_shop.id,
            supplier_product_id=sproduct.id,
            margin_percent=MARGIN,
            sync_enabled=True,
            sync_price=True,
            sync_inventory=True,
            status="active",
        )
        session.add(listing)
        await session.flush()

        # Link each supplier variant to a seller variant with calculated price
        sv_stmt = select(SupplierVariant).filter_by(supplier_product_id=sproduct.id)
        result = await session.execute(sv_stmt)
        supplier_variants = result.scalars().all()

        for sv in supplier_variants:
            calculated_price = sv.cost_price * (1 + MARGIN / 100)
            seller_variant = SellerVariant(
                listing_id=listing.id,
                supplier_variant_id=sv.id,
                price=calculated_price,
                inventory_cache=sv.inventory,
                is_enabled=True,
            )
            session.add(seller_variant)

        await session.flush()
        print(f"  [add ] SellerListing for '{sproduct.title}'")
        listings.append(listing)

    return listings


async def seed_orders(session, seller_shop, supplier_shop, listings):
    """Create 2 orders in different states: pending and paid."""
    from src.domains.orders.models import Order, OrderItem, OrderStatus
    from src.domains.products.models import ProductVariant, SellerListing, SellerVariant

    created_any = False

    for order_state in ["pending", "paid"]:
        existing = await get_one(
            session, Order, shop_id=seller_shop.id, status=order_state
        )
        if existing:
            print(f"  [skip] Order with status '{order_state}' already exists")
            continue

        # Pick a listing and its variant to build the order item
        listing = listings[0] if order_state == "pending" else listings[1]
        sv_stmt = select(SellerVariant).filter_by(listing_id=listing.id)
        result = await session.execute(sv_stmt)
        seller_variant = result.scalars().first()
        if not seller_variant:
            print(f"  [warn] No seller variant for listing {listing.id}, skipping order")
            continue

        # Get the product variant for the order item FK
        pv_stmt = select(ProductVariant).filter_by(id=seller_variant.supplier_variant_id)
        # Actually the order_item.variant_id points to product_variants.id,
        # but we need the variant_id from the supplier_variant record
        from src.domains.products.models import SupplierVariant as SV
        sup_var = await get_one(session, SV, id=seller_variant.supplier_variant_id)

        total_price = seller_variant.price
        now = datetime.now(timezone.utc)

        order_kwargs = dict(
            shop_id=seller_shop.id,
            total_price=total_price,
            shipping_price=Decimal(0),
            discount=Decimal(0),
            status=order_state,
            customer_data={"name": "مشتری تست", "phone": "09333333333"},
        )
        if order_state == "paid":
            order_kwargs["paid_at"] = now

        order = Order(**order_kwargs)
        session.add(order)
        await session.flush()

        order_item = OrderItem(
            order_id=order.id,
            supplier_shop_id=supplier_shop.id,
            variant_id=sup_var.variant_id,
            seller_listing_id=listing.id,
            quantity=1,
            supplier_price=sup_var.cost_price,
            seller_price=seller_variant.price,
            shipping_price=Decimal(0),
            profit=seller_variant.price - sup_var.cost_price,
            status=order_state,
        )
        session.add(order_item)
        await session.flush()

        print(f"  [add ] Order ({order_state}) total={total_price}")
        created_any = True

    return created_any


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("=" * 60)
    print("Seed Data Script")
    print("=" * 60)

    async with async_session_maker() as session:
        try:
            print("\n[1/6] Seeding platforms ...")
            await seed_platforms(session)

            print("\n[2/6] Seeding users ...")
            admin, supplier_user, supplier_account, seller_user, seller_account = (
                await seed_users(session)
            )

            print("\n[3/6] Seeding shops ...")
            supplier_shop, seller_shop = await seed_shops(
                session, supplier_account, seller_account
            )

            print("\n[4/6] Seeding categories ...")
            categories = await seed_categories(session)

            print("\n[5/6] Seeding supplier products ...")
            products = await seed_supplier_products(session, supplier_shop, categories)

            print("\n[6a] Seeding seller listings ...")
            listings = await seed_seller_listings(session, seller_shop, products)

            print("\n[6b] Seeding orders ...")
            await seed_orders(session, seller_shop, supplier_shop, listings)

            await session.commit()
            print("\n" + "=" * 60)
            print("Seed data completed successfully.")
            print("=" * 60)

        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
