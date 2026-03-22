from typing import List, Dict, Any, Optional

from ..connector import (
    ShopConnector,
    ConnectionResult,
    Product,
    Inventory,
    Order,
)


class ShopifyConnector(ShopConnector):
    PLATFORM_CODE = "shopify"

    def __init__(self, credentials: Optional[Dict[str, Any]] = None):
        super().__init__(credentials)
        self._client = None

    async def connect(self, credentials: Dict[str, Any]) -> ConnectionResult:
        return ConnectionResult(
            success=False, message="Shopify connector not yet implemented"
        )

    async def disconnect(self) -> bool:
        return True

    async def test_connection(self) -> bool:
        return False

    async def get_products(self) -> List[Product]:
        raise NotImplementedError("Shopify connector not yet implemented")

    async def get_product(self, product_id: str) -> Product:
        raise NotImplementedError("Shopify connector not yet implemented")

    async def get_inventory(self, variant_id: str) -> Inventory:
        raise NotImplementedError("Shopify connector not yet implemented")

    async def update_inventory(self, variant_id: str, quantity: int) -> Inventory:
        raise NotImplementedError("Shopify connector not yet implemented")

    async def get_orders(self) -> List[Order]:
        raise NotImplementedError("Shopify connector not yet implemented")

    async def get_order(self, order_id: str) -> Order:
        raise NotImplementedError("Shopify connector not yet implemented")

    async def register_webhook(self, url: str, events: List[str]) -> str:
        raise NotImplementedError("Shopify connector not yet implemented")

    async def delete_webhook(self, webhook_id: str) -> bool:
        raise NotImplementedError("Shopify connector not yet implemented")
