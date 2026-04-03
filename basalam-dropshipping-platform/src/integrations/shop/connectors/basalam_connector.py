from datetime import datetime
from typing import List, Optional, Dict, Any

from ..connector import (
    ShopConnector,
    ConnectionResult,
    Product,
    ProductVariant,
    Inventory,
    Order,
    OrderItem,
)
from ...basalam.client import BasalamClient
from ...basalam.exceptions import BasalamAPIError


class BasalamConnector(ShopConnector):
    PLATFORM_CODE = "basalam"

    def __init__(self, credentials: Optional[Dict[str, Any]] = None):
        super().__init__(credentials)
        self._client: Optional[BasalamClient] = None
        self._vendor_id: Optional[str] = None

    @property
    def vendor_id(self) -> Optional[str]:
        """Get vendor_id from credentials or explicitly set value."""
        return self._vendor_id or (self._credentials.get("vendor_id") if self._credentials else None)

    def set_vendor_id(self, vendor_id: str) -> None:
        """Explicitly set vendor_id (useful when extracted from external_shop_id)."""
        self._vendor_id = vendor_id

    def _get_client(self) -> BasalamClient:
        if self._client is None:
            creds = self._credentials or {}
            self._client = BasalamClient(
                client_id=creds.get("client_id", ""),
                client_secret=creds.get("client_secret", ""),
                access_token=creds.get("access_token"),
                refresh_token=creds.get("refresh_token"),
            )
        return self._client

    async def connect(self, credentials: Dict[str, Any]) -> ConnectionResult:
        self._credentials = credentials

        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")

        if not client_id or not client_secret:
            return ConnectionResult(
                success=False, message="client_id and client_secret are required"
            )

        try:
            client = self._get_client()
            token_data = await client.get_access_token()

            self._connected = True
            expires_at = datetime.utcnow() if token_data.get("expires_in") else None

            return ConnectionResult(
                success=True,
                message="Connected to Basalam successfully",
                connected_at=datetime.utcnow(),
                expires_at=expires_at,
                extra={
                    "access_token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),
                },
            )
        except BasalamAPIError as e:
            return ConnectionResult(
                success=False, message=f"Failed to connect: {e.message}"
            )
        except Exception as e:
            return ConnectionResult(
                success=False, message=f"Connection failed: {str(e)}"
            )

    async def disconnect(self) -> bool:
        if self._client:
            await self._client.close()
            self._client = None
        self._connected = False
        self._credentials = None
        return True

    async def test_connection(self) -> bool:
        if not self._connected:
            return False

        try:
            client = self._get_client()
            await client.list_products(vendor_id=self.vendor_id, page=1, per_page=1)
            return True
        except Exception:
            return False

    async def get_products(self) -> List[Product]:
        await self._ensure_connected()
        client = self._get_client()
        vendor_id = self.vendor_id

        products = []
        page = 1
        per_page = 50

        while True:
            result = await client.list_products(vendor_id=vendor_id, page=page, per_page=per_page)
            product_list = result.get("products", [])
            pagination = result.get("pagination", {})
            total_pages = pagination.get("total_pages", pagination.get("total_page", 1))

            for p in product_list:
                products.append(self._map_product(p))

            if page >= total_pages:
                break
            page += 1

        return products

    async def get_product(self, product_id: str) -> Product:
        await self._ensure_connected()
        client = self._get_client()

        product_data = await client.get_product(product_id)
        return self._map_product(product_data)

    async def get_inventory(self, variant_id: str) -> Inventory:
        await self._ensure_connected()
        client = self._get_client()

        product_id = variant_id.split("-")[0] if "-" in variant_id else variant_id
        inventory_data = await client.get_inventory(product_id)

        variants = inventory_data.get("variants", [])
        for v in variants:
            if v.get("variant_id") == variant_id:
                return Inventory(
                    variant_id=v.get("variant_id", variant_id),
                    quantity=v.get("stock", 0),
                    reserved=v.get("reserved", 0),
                    available=v.get("available", 0),
                )

        return Inventory(
            variant_id=variant_id,
            quantity=0,
            reserved=0,
            available=0,
        )

    async def update_inventory(self, variant_id: str, quantity: int) -> Inventory:
        await self._ensure_connected()
        client = self._get_client()

        result = await client.update_inventory(variant_id, quantity)

        return Inventory(
            variant_id=result.get("variant_id", variant_id),
            quantity=result.get("quantity", quantity),
            updated_at=datetime.utcnow(),
        )

    async def get_orders(self) -> List[Order]:
        await self._ensure_connected()
        client = self._get_client()

        orders = []
        page = 1

        while True:
            result = await client.list_orders(page=page)
            order_list = result.get("orders", [])
            pagination = result.get("pagination", {})
            total_pages = pagination.get("total_pages", 1)

            for o in order_list:
                orders.append(self._map_order(o))

            if page >= total_pages:
                break
            page += 1

        return orders

    async def get_order(self, order_id: str) -> Order:
        await self._ensure_connected()
        client = self._get_client()

        order_data = await client.get_order(order_id)
        return self._map_order(order_data)

    async def register_webhook(self, url: str, events: List[str]) -> str:
        await self._ensure_connected()
        client = self._get_client()

        result = await client.register_webhook(url, events)
        return result.get("webhook_id", "")

    async def delete_webhook(self, webhook_id: str) -> bool:
        await self._ensure_connected()
        client = self._get_client()

        await client.delete_webhook(webhook_id)
        return True

    def _map_product(self, data: Dict[str, Any]) -> Product:
        variants = []
        for v in data.get("variants", []):
            variants.append(
                ProductVariant(
                    variant_id=v.get("variant_id", v.get("id", "")),
                    sku=v.get("sku"),
                    title=v.get("title"),
                    price=v.get("price"),
                    inventory=v.get("inventory", v.get("stock", 0)),
                    attributes=v.get("attributes", {}),
                )
            )

        # Handle both 'id' (real Basalam) and 'product_id' (legacy)
        product_id = str(data.get("product_id") or data.get("id", ""))

        return Product(
            product_id=product_id,
            title=data.get("title", ""),
            description=data.get("description", ""),
            price=float(data.get("price", 0)),
            category=data.get("category"),
            images=data.get("images", []),
            variants=variants,
            status=data.get("status", "active"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            metadata=data.get("metadata", {}),
        )

    def _map_order(self, data: Dict[str, Any]) -> Order:
        items = []
        for item in data.get("items", []):
            items.append(
                OrderItem(
                    item_id=item.get("item_id", ""),
                    product_id=item.get("product_id", ""),
                    variant_id=item.get("variant_id"),
                    title=item.get("title", ""),
                    quantity=item.get("quantity", 0),
                    price=float(item.get("price", 0)),
                    metadata=item.get("metadata", {}),
                )
            )

        return Order(
            order_id=data.get("order_id", ""),
            customer=data.get("customer", {}),
            items=items,
            total_price=float(data.get("total_price", 0)),
            shipping_price=float(data.get("shipping_price", 0)),
            status=data.get("status", "pending"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            metadata=data.get("metadata", {}),
        )
