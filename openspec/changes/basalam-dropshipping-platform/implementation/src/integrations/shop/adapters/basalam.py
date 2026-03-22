"""
Basalam Shop Connector Adapter
===============================
Implements ShopConnectorPort for Basalam platform

This is an ADAPTER in Hexagonal Architecture:
- Implements the Port interface (ports.py)
- Handles Basalam-specific API calls
- Translates Basalam API responses to internal models
"""
import httpx
import hashlib
import hmac
from datetime import datetime, timedelta
from uuid import UUID
from typing import List, Optional, Dict, Any

from ..ports import (
    ShopConnectorPort,
    ShopProducts,
    ShopOrder,
    ShopCredentials,
    OAuthConfig,
)


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
    
    API_BASE_URL = "https://api.basalam.com"
    
    def __init__(self, credentials: Optional[ShopCredentials] = None):
        self.credentials = credentials
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def platform_code(self) -> str:
        return "basalam"
    
    @property
    def oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            client_id="{{BASALAM_CLIENT_ID}}",
            client_secret="{{BASALAM_CLIENT_SECRET}}",
            authorize_url=f"{self.API_BASE_URL}/oauth/authorize",
            token_url=f"{self.API_BASE_URL}/oauth/token",
            redirect_uri="{{BASE_URL}}/integrations/basalam/callback",
            scopes=[
                "vendor.products.read",
                "vendor.products.write",
                "vendor.orders.read",
                "vendor.orders.write",
                "vendor.inventory.write",
                "vendor.shipping.read",
                "vendor.webhooks.write",
            ]
        )
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with auth headers"""
        if self._client is None:
            headers = {}
            if self.credentials and self.credentials.access_token:
                headers["Authorization"] = f"Bearer {self.credentials.access_token}"
            
            self._client = httpx.AsyncClient(
                base_url=self.API_BASE_URL,
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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "/oauth/token",
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
        """Fetch products from Basalam"""
        client = await self._get_client()
        
        response = await client.get(
            "/vendor/products",
            params={
                "page": page,
                "limit": limit,
                "status": "active"
            }
        )
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        products = []
        
        for item in data.get("data", []):
            products.append(ShopProducts(
                external_product_id=str(item["product_id"]),
                title=item.get("title", ""),
                description=item.get("description", ""),
                price=float(item.get("price", 0)),
                inventory=int(item.get("inventory", 0)),
                category=item.get("category"),
                images=[img["url"] for img in item.get("images", [])],
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
        
        return ShopProducts(
            external_product_id=str(item["product_id"]),
            title=item.get("title", ""),
            description=item.get("description", ""),
            price=float(item.get("price", 0)),
            inventory=int(item.get("inventory", 0)),
            category=item.get("category"),
            images=[img["url"] for img in item.get("images", [])],
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
        """Register webhook with Basalam"""
        client = await self._get_client()
        
        response = await client.post(
            "/vendor/webhooks",
            json={
                "url": webhook_url,
                "events": event_types
            }
        )
        
        return response.status_code in [200, 201]
    
    async def unregister_webhook(self, webhook_id: str) -> bool:
        """Unregister webhook"""
        client = await self._get_client()
        
        response = await client.delete(f"/vendor/webhooks/{webhook_id}")
        
        return response.status_code == 204
    
    async def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Basalam webhook signature"""
        if not self.credentials:
            return False
        
        secret = self.credentials.extra.get("webhook_secret", "")
        expected_signature = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    
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
