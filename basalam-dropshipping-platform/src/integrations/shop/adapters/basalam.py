"""
Basalam Shop Connector Adapter
===============================
Implements ShopConnectorPort for Basalam platform

This is an ADAPTER in Hexagonal Architecture:
- Implements the Port interface (ports.py)
- Handles Basalam-specific API calls
- Translates Basalam API responses to internal models
"""
import hashlib
import hmac
import structlog
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import httpx

from src.core.config import get_settings
from ..ports import (
    ShopConnectorPort,
    ShopProducts,
    ShopOrder,
    ShopCredentials,
    OAuthConfig,
)

logger = structlog.get_logger(__name__)


class BasalamConnectorAdapter(ShopConnectorPort):
    """
    Basalam-specific implementation of ShopConnectorPort

    Handles:
    - OAuth authentication with Basalam
    - Product sync (products, variants, images)
    - Order sync
    - Inventory updates
    - Webhook management
    - Category detection
    """

    # Basalam numeric event IDs for webhooks
    EVENT_PRODUCT_CHANGES = 8
    EVENT_NEW_ORDER = 5
    EVENT_PARCEL_CHANGES = 7

    def __init__(self, credentials: Optional[ShopCredentials] = None):
        self.credentials = credentials
        self._client: Optional[httpx.AsyncClient] = None
        self._vendor_id: Optional[str] = None

    def set_vendor_id(self, vendor_id: str) -> None:
        """Set vendor_id explicitly (extracted from integration.external_shop_id)."""
        self._vendor_id = vendor_id

    @property
    def platform_code(self) -> str:
        return "basalam"

    @property
    def oauth_config(self) -> OAuthConfig:
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
            ]
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with auth headers"""
        if self._client is None:
            headers = {}
            if self.credentials and self.credentials.access_token:
                headers["Authorization"] = f"Bearer {self.credentials.access_token}"

            settings = get_settings()
            self._client = httpx.AsyncClient(
                base_url=settings.basalam_api_url,
                headers=headers,
                timeout=30.0
            )
        return self._client
    
    async def connect(self, credentials: ShopCredentials) -> bool:
        """Connect to Basalam using credentials"""
        self.credentials = credentials
        
        # Verify connection by fetching vendor info
        return await self.verify_connection()
    
    async def disconnect(self) -> bool:
        """Disconnect from Basalam"""
        if self._client:
            await self._client.aclose()
            self._client = None
        self.credentials = None
        return True
    
    async def verify_connection(self) -> bool:
        """Verify connection is valid"""
        try:
            client = await self._get_client()
            response = await client.get("/vendor/info")
            return response.status_code == 200
        except Exception:
            return False
    
    async def refresh_credentials(self, credentials: ShopCredentials) -> ShopCredentials:
        """Refresh expired Basalam tokens"""
        _s = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_s.basalam_auth_url}/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": credentials.refresh_token,
                    "client_id": self.oauth_config.client_id,
                    "client_secret": self.oauth_config.client_secret,
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                credentials.access_token = data["access_token"]
                credentials.refresh_token = data["refresh_token"]
                credentials.token_expires_at = datetime.utcnow() + timedelta(
                    seconds=data.get("expires_in", 3600)
                )
            
            return credentials
    
    # ---- Product Operations ----
    
    async def fetch_products(self, page: int = 1, limit: int = 50) -> List[ShopProducts]:
        """Fetch products from Basalam.

        Calls GET /vendors/{vendor_id}/products with page-based pagination.
        The vendor_id must be set via credentials or set_vendor_id().
        """
        vendor_id = self._vendor_id
        if not vendor_id:
            logger.warning("No vendor_id available for fetch_products")
            return []

        client = await self._get_client()

        response = await client.get(
            f"/vendors/{vendor_id}/products",
            params={
                "page": page,
                "per_page": limit,
            }
        )

        if response.status_code != 200:
            return []

        data = response.json()
        products = []

        for item in data.get("data", []):
            # Real Basalam shape: id (not product_id), photo{original, id}
            photo = item.get("photo", {})
            images = [photo["original"]] if photo and photo.get("original") else []

            products.append(ShopProducts(
                external_product_id=str(item.get("id", item.get("product_id", ""))),
                title=item.get("title", ""),
                description=item.get("description", ""),
                price=float(item.get("price", 0)),
                inventory=int(item.get("inventory", 0)),
                category=item.get("category"),
                images=images,
                variants=item.get("variants", []),
                status=item.get("status", "active")
            ))

        return products
    
    async def fetch_product(self, product_id: str) -> ShopProducts:
        """Fetch single product"""
        client = await self._get_client()
        
        response = await client.get(f"/vendor/products/{product_id}")
        
        if response.status_code != 200:
            raise ValueError(f"Product {product_id} not found")
        
        item = response.json()

        # Real Basalam shape: id (not product_id), photo{original, id}
        photo = item.get("photo", {})
        images = [photo["original"]] if photo and photo.get("original") else []

        return ShopProducts(
            external_product_id=str(item.get("id", item.get("product_id", ""))),
            title=item.get("title", ""),
            description=item.get("description", ""),
            price=float(item.get("price", 0)),
            inventory=int(item.get("inventory", 0)),
            category=item.get("category"),
            images=images,
            variants=item.get("variants", []),
            status=item.get("status", "active")
        )
    
    async def fetch_product_variants(self, product_id: str) -> List[Dict[str, Any]]:
        """Fetch variants for a product"""
        client = await self._get_client()
        
        response = await client.get(f"/vendor/products/{product_id}/variants")
        
        if response.status_code == 200:
            return response.json().get("data", [])
        
        return []
    
    # ---- Order Operations ----
    
    async def fetch_orders(self, since: Optional[datetime] = None, page: int = 1) -> List[ShopOrder]:
        """Fetch orders from Basalam"""
        client = await self._get_client()
        
        params = {"page": page}
        if since:
            params["since"] = since.isoformat()
        
        response = await client.get("/vendor/orders", params=params)
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        orders = []
        
        for item in data.get("data", []):
            orders.append(ShopOrder(
                external_order_id=str(item["order_id"]),
                customer_data=item.get("customer", {}),
                items=item.get("items", []),
                total_price=float(item.get("total_price", 0)),
                shipping_price=float(item.get("shipping_price", 0)),
                status=item.get("status", "pending")
            ))
        
        return orders
    
    async def fetch_order(self, order_id: str) -> ShopOrder:
        """Fetch single order"""
        client = await self._get_client()
        
        response = await client.get(f"/vendor/orders/{order_id}")
        
        if response.status_code != 200:
            raise ValueError(f"Order {order_id} not found")
        
        item = response.json()
        
        return ShopOrder(
            external_order_id=str(item["order_id"]),
            customer_data=item.get("customer", {}),
            items=item.get("items", []),
            total_price=float(item.get("total_price", 0)),
            shipping_price=float(item.get("shipping_price", 0)),
            status=item.get("status", "pending")
        )
    
    # ---- Inventory Operations ----
    
    async def update_inventory(self, variant_id: str, quantity: int) -> bool:
        """Update inventory for a variant"""
        client = await self._get_client()
        
        response = await client.patch(
            f"/vendor/variants/{variant_id}/inventory",
            json={"inventory": quantity}
        )
        
        return response.status_code == 200
    
    # ---- Webhook Operations ----
    
    async def register_webhook(self, webhook_url: str, event_types: List[str]) -> bool:
        """Register webhook with Basalam using numeric event_ids.

        Uses settings.basalam_webhook_url for the correct endpoint.
        Event IDs: 8=PRODUCT_CREATE_CHANGES, 5=VENDOR_NEW_ORDER, 7=VENDOR_PARCEL_CHANGES
        """
        _s = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_s.basalam_webhook_url}/webhooks",
                headers={"Authorization": f"Bearer {self.credentials.access_token}"}
                if self.credentials and self.credentials.access_token else {},
                json={
                    "event_ids": [self.EVENT_PRODUCT_CHANGES, self.EVENT_NEW_ORDER, self.EVENT_PARCEL_CHANGES],
                    "request_method": "POST",
                    "url": webhook_url,
                    "is_active": True,
                    "register_me": True,
                }
            )

            return response.status_code in [200, 201]
    
    async def unregister_webhook(self, webhook_id: str) -> bool:
        """Unregister webhook using Basalam webhook service URL"""
        _s = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{_s.basalam_webhook_url}/webhooks/{webhook_id}",
                headers=(
                    {"Authorization": f"Bearer {self.credentials.access_token}"}
                    if self.credentials and self.credentials.access_token else {}
                ),
            )
            return response.status_code in [200, 204]
    
    async def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Basalam webhook signature (HMAC-SHA256).

        Basalam sends ``X-Basalam-Signature: sha256=<hex>`` — the ``sha256=``
        prefix must be stripped before comparing with the computed digest.
        """
        if not self.credentials:
            return False

        secret = self.credentials.extra.get("webhook_secret", "")
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Strip the "sha256=" prefix if present
        received = signature.removeprefix("sha256=")

        return hmac.compare_digest(received, expected)
    
    # ---- Shipping Operations ----
    
    async def fetch_shipping_methods(self) -> List[Dict[str, Any]]:
        """Fetch available shipping methods"""
        client = await self._get_client()
        
        response = await client.get("/vendor/shipping/methods")
        
        if response.status_code == 200:
            return response.json().get("data", [])
        
        return []
    
    async def create_shipment(self, order_id: str, shipping_method: str) -> Dict[str, Any]:
        """Create shipment for order"""
        client = await self._get_client()
        
        response = await client.post(
            f"/vendor/orders/{order_id}/ship",
            json={"shipping_method": shipping_method}
        )
        
        if response.status_code in [200, 201]:
            return response.json()
        
        raise ValueError("Failed to create shipment")
    
    # ---- Category Operations ----
    
    async def detect_category(self, product_title: str, description: str) -> Optional[Dict[str, Any]]:
        """Detect product category using Basalam's AI"""
        client = await self._get_client()
        
        response = await client.post(
            "/ai/category/detect",
            json={
                "title": product_title,
                "description": description
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get("category")
        
        return None
