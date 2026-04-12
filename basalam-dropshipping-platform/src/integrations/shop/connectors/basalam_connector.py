"""
Basalam Connector — legacy + ShopConnectorPort implementation.

This connector extends BaseShopConnector (which implements ShopConnectorPort
from the hexagonal architecture).  It retains the legacy method names
(get_products, get_orders, etc.) used by integration_service.py while
also satisfying the canonical port interface.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any

from ..connector import (
    BaseShopConnector,
    Product,
    ProductVariant,
    Inventory,
    Order,
    OrderItem,
)
from ..ports import (
    ShopProducts,
    ShopOrder,
    ShopCredentials,
    OAuthConfig,
)
from ...basalam.client import BasalamClient
from ...basalam.exceptions import BasalamAPIError


class BasalamConnector(BaseShopConnector):
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

    # ------------------------------------------------------------------
    # ShopConnectorPort — abstract property
    # ------------------------------------------------------------------

    @property
    def oauth_config(self) -> OAuthConfig:
        from src.core.config import get_settings
        _s = get_settings()
        return OAuthConfig(
            client_id=_s.basalam_client_id,
            client_secret=_s.basalam_client_secret.get_secret_value(),
            authorize_url="https://basalam.com/accounts/sso",
            token_url=f"{_s.basalam_auth_url}/oauth/token",
            redirect_uri=f"{_s.base_url}/api/v1/shops/integrations/basalam/callback",
            scopes=[
                "vendor.product.read",
                "vendor.parcel.read",
                "vendor.shipping.read",
            ],
        )

    # ------------------------------------------------------------------
    # ShopConnectorPort — connection methods
    # ------------------------------------------------------------------

    async def connect(self, credentials) -> bool:
        """Connect to Basalam.

        Accepts either a ShopCredentials (port interface) or a plain dict
        (legacy interface).  Returns True/False for port compatibility.
        """
        # Normalise input — legacy callers pass a plain dict.
        if isinstance(credentials, ShopCredentials):
            cred_dict = credentials.extra
            self._credentials = cred_dict
        else:
            cred_dict = credentials
            self._credentials = credentials

        client_id = cred_dict.get("client_id")
        client_secret = cred_dict.get("client_secret")

        if not client_id or not client_secret:
            return False

        try:
            client = self._get_client()
            await client.get_access_token()
            self._connected = True
            return True
        except (BasalamAPIError, Exception):
            return False

    async def disconnect(self) -> bool:
        if self._client:
            await self._client.close()
            self._client = None
        self._connected = False
        self._credentials = None
        return True

    async def verify_connection(self) -> bool:
        if not self._connected:
            return False
        try:
            client = self._get_client()
            await client.list_products(vendor_id=self.vendor_id, page=1, per_page=1)
            return True
        except Exception:
            return False

    async def refresh_credentials(self, credentials: ShopCredentials) -> ShopCredentials:
        """Refresh expired Basalam tokens."""
        import httpx

        _s = None
        try:
            from src.core.config import get_settings
            _s = get_settings()
        except Exception:
            pass

        async with httpx.AsyncClient() as http_client:
            base_url = (_s.basalam_auth_url if _s else "").rstrip("/") or "https://auth.basalam.com"
            response = await http_client.post(
                f"{base_url}/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": credentials.refresh_token,
                    "client_id": self.oauth_config.client_id,
                    "client_secret": self.oauth_config.client_secret,
                },
            )
            if response.status_code == 200:
                data = response.json()
                credentials.access_token = data["access_token"]
                credentials.refresh_token = data["refresh_token"]
            return credentials

    # ------------------------------------------------------------------
    # ShopConnectorPort — product operations
    # ------------------------------------------------------------------

    async def fetch_products(self, page: int = 1, limit: int = 50) -> List[ShopProducts]:
        await self._ensure_connected()
        client = self._get_client()
        vendor_id = self.vendor_id

        result = await client.list_products(vendor_id=vendor_id, page=page, per_page=limit)
        product_list = result.get("products", [])

        products: list[ShopProducts] = []
        for p in product_list:
            products.append(self._map_to_shop_product(p))

        return products

    async def fetch_product(self, product_id: str) -> ShopProducts:
        await self._ensure_connected()
        client = self._get_client()
        product_data = await client.get_product(product_id)
        return self._map_to_shop_product(product_data)

    async def fetch_product_variants(self, product_id: str) -> List[Dict[str, Any]]:
        await self._ensure_connected()
        product = await self.get_product(product_id)
        return [
            {
                "variant_id": v.variant_id,
                "sku": v.sku,
                "title": v.title,
                "price": v.price,
                "inventory": v.inventory,
                "attributes": v.attributes,
            }
            for v in product.variants
        ]

    # ------------------------------------------------------------------
    # ShopConnectorPort — order operations
    # ------------------------------------------------------------------

    async def fetch_orders(self, since: Optional[datetime] = None, page: int = 1) -> List[ShopOrder]:
        await self._ensure_connected()
        client = self._get_client()

        result = await client.list_orders(page=page)
        order_list = result.get("orders", [])

        orders: list[ShopOrder] = []
        for o in order_list:
            orders.append(self._map_to_shop_order(o))

        return orders

    async def fetch_order(self, order_id: str) -> ShopOrder:
        await self._ensure_connected()
        client = self._get_client()
        order_data = await client.get_order(order_id)
        return self._map_to_shop_order(order_data)

    # ------------------------------------------------------------------
    # ShopConnectorPort — inventory operations
    # ------------------------------------------------------------------

    async def update_inventory(self, variant_id: str, quantity: int) -> bool:
        await self._ensure_connected()
        client = self._get_client()
        try:
            await client.update_inventory(variant_id, quantity)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # ShopConnectorPort — webhook operations
    # ------------------------------------------------------------------

    async def register_webhook(self, webhook_url: str, event_types: List[str]) -> bool:
        await self._ensure_connected()
        client = self._get_client()
        try:
            await client.register_webhook(webhook_url, event_types)
            return True
        except Exception:
            return False

    async def unregister_webhook(self, webhook_id: str) -> bool:
        await self._ensure_connected()
        client = self._get_client()
        try:
            await client.delete_webhook(webhook_id)
            return True
        except Exception:
            return False

    async def update_webhook(self, webhook_id: str, config: Dict[str, Any]) -> bool:
        """Update an existing webhook's configuration on Basalam."""
        await self._ensure_connected()
        client = self._get_client()
        try:
            await client.update_webhook(webhook_id, config)
            return True
        except Exception:
            return False

    async def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        import hashlib
        import hmac

        if not self._credentials:
            return False
        secret = self._credentials.get("webhook_secret", "")
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        received = signature.removeprefix("sha256=")
        return hmac.compare_digest(received, expected)

    # ------------------------------------------------------------------
    # ShopConnectorPort — shipping operations
    # ------------------------------------------------------------------

    async def fetch_shipping_methods(self) -> List[Dict[str, Any]]:
        # Not supported by the legacy BasalamClient; return empty.
        return []

    async def create_shipment(self, order_id: str, shipping_method: str) -> Dict[str, Any]:
        # Not supported by the legacy BasalamClient.
        raise NotImplementedError("Shipment creation not available via legacy connector")

    # ------------------------------------------------------------------
    # ShopConnectorPort — category operations
    # ------------------------------------------------------------------

    async def detect_category(self, product_title: str, description: str) -> Optional[Dict[str, Any]]:
        # Not supported by the legacy BasalamClient.
        return None

    # ------------------------------------------------------------------
    # Legacy convenience methods (used by integration_service.py)
    # These are NOT part of ShopConnectorPort but are kept for backward
    # compatibility with existing callers.
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Legacy alias for verify_connection()."""
        return await self.verify_connection()

    async def get_products(self) -> List[Product]:
        """Fetch all products (legacy interface, paginates internally)."""
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
        """Fetch single product (legacy interface)."""
        await self._ensure_connected()
        client = self._get_client()
        product_data = await client.get_product(product_id)
        return self._map_product(product_data)

    async def get_inventory(self, variant_id: str) -> Inventory:
        """Fetch inventory for a variant (legacy interface)."""
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

    async def get_orders(self) -> List[Order]:
        """Fetch all orders (legacy interface, paginates internally)."""
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
        """Fetch single order (legacy interface)."""
        await self._ensure_connected()
        client = self._get_client()
        order_data = await client.get_order(order_id)
        return self._map_order(order_data)

    async def delete_webhook(self, webhook_id: str) -> bool:
        """Legacy alias for unregister_webhook()."""
        return await self.unregister_webhook(webhook_id)

    # ------------------------------------------------------------------
    # Private mappers
    # ------------------------------------------------------------------

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

    def _map_to_shop_product(self, data: Dict[str, Any]) -> ShopProducts:
        """Map raw API data to the canonical ShopProducts model."""
        return ShopProducts(
            external_product_id=str(data.get("product_id") or data.get("id", "")),
            title=data.get("title", ""),
            description=data.get("description", ""),
            price=float(data.get("price", 0)),
            inventory=int(data.get("inventory", data.get("stock", 0))),
            category=data.get("category"),
            images=data.get("images", []),
            variants=data.get("variants", []),
            status=data.get("status", "active"),
        )

    def _map_to_shop_order(self, data: Dict[str, Any]) -> ShopOrder:
        """Map raw API data to the canonical ShopOrder model."""
        return ShopOrder(
            external_order_id=str(data.get("order_id", "")),
            customer_data=data.get("customer", {}),
            items=data.get("items", []),
            total_price=float(data.get("total_price", 0)),
            shipping_price=float(data.get("shipping_price", 0)),
            status=data.get("status", "pending"),
        )
