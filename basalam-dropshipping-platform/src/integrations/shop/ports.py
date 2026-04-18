"""
Shop Integration Ports - Hexagonal Architecture
==============================================
This is the PRIMARY ADAPTER interface.
All shop integrations (Basalam, Shopify, WooCommerce) implement this port.

Using Ports & Adapters (Hexagonal) Pattern:
- Port: Abstract interface (this file)
- Adapters: Concrete implementations (basalam.py, shopify.py)
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


# ============================================
# PORT INTERFACES (Abstract Contracts)
# ============================================

class ShopProducts(BaseModel):
    """Product data from any shop platform"""
    external_product_id: str
    title: str
    description: str
    price: int
    inventory: int
    category: Optional[Dict[str, Any]] = None
    images: List[str] = []
    variants: List[Dict[str, Any]] = []
    status: str = "active"


class ShopOrder(BaseModel):
    """Order data from any shop platform"""
    external_order_id: str
    customer_data: Dict[str, Any]
    items: List[Dict[str, Any]]
    total_price: int
    shipping_price: int = 0
    status: str


class ShopCredentials(BaseModel):
    """Credentials needed to connect to a shop"""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    api_key: Optional[str] = None
    shop_url: Optional[str] = None
    extra: Dict[str, Any] = {}


class OAuthConfig(BaseModel):
    """OAuth configuration for connecting to a shop"""
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    redirect_uri: str
    scopes: List[str] = []


# ============================================
# SHOP CONNECTOR PORT (Primary Port)
# ============================================

class ShopConnectorPort(ABC):
    """
    PRIMARY PORT - Abstract interface for shop integrations
    
    All shop adapters MUST implement this port.
    This allows the core domain to be independent of specific platform APIs.
    
    Usage:
        connector = BasalamConnector()
        products = await connector.fetch_products()
    """
    
    @property
    @abstractmethod
    def platform_code(self) -> str:
        """Unique code for this platform (e.g., 'basalam', 'shopify')"""
        pass
    
    @property
    @abstractmethod
    def oauth_config(self) -> OAuthConfig:
        """OAuth configuration for this platform"""
        pass
    
    @abstractmethod
    async def connect(self, credentials: ShopCredentials) -> bool:
        """
        Establish connection to shop
        Returns True if successful
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from shop"""
        pass
    
    @abstractmethod
    async def verify_connection(self) -> bool:
        """Verify if connection is still valid"""
        pass
    
    @abstractmethod
    async def refresh_credentials(self, credentials: ShopCredentials) -> ShopCredentials:
        """Refresh expired credentials"""
        pass
    
    # ---- Product Operations ----
    
    @abstractmethod
    async def fetch_products(self, page: int = 1, limit: int = 50) -> List[ShopProducts]:
        """Fetch products from shop with pagination"""
        pass
    
    @abstractmethod
    async def fetch_product(self, product_id: str) -> ShopProducts:
        """Fetch single product by ID"""
        pass
    
    @abstractmethod
    async def fetch_product_variants(self, product_id: str) -> List[Dict[str, Any]]:
        """Fetch variants for a product"""
        pass
    
    # ---- Order Operations ----
    
    @abstractmethod
    async def fetch_orders(self, since: Optional[datetime] = None, page: int = 1) -> List[ShopOrder]:
        """Fetch orders since given datetime"""
        pass
    
    @abstractmethod
    async def fetch_order(self, order_id: str) -> ShopOrder:
        """Fetch single order by ID"""
        pass
    
    # ---- Inventory Operations ----
    
    @abstractmethod
    async def update_inventory(self, variant_id: str, quantity: int) -> bool:
        """Update inventory for a variant"""
        pass
    
    # ---- Webhook Operations ----
    
    @abstractmethod
    async def register_webhook(self, webhook_url: str, event_types: List[str]) -> bool:
        """Register webhook endpoint for events"""
        pass
    
    @abstractmethod
    async def unregister_webhook(self, webhook_id: str) -> bool:
        """Unregister webhook"""
        pass
    
    @abstractmethod
    async def update_webhook(self, webhook_id: str, config: Dict[str, Any]) -> bool:
        """Update an existing webhook's configuration (secret, URL, etc.)"""
        pass

    @abstractmethod
    async def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature for security"""
        pass
    
    # ---- Shipping Operations ----
    
    @abstractmethod
    async def fetch_shipping_methods(self) -> List[Dict[str, Any]]:
        """Fetch available shipping methods"""
        pass
    
    @abstractmethod
    async def create_shipment(self, order_id: str, shipping_method: str) -> Dict[str, Any]:
        """Create shipment for order"""
        pass
    
    # ---- Category Operations ----
    
    @abstractmethod
    async def detect_category(self, product_title: str, description: str) -> Optional[Dict[str, Any]]:
        """Detect product category using platform's AI"""
        pass


# ============================================
# SHOP REGISTRY - Port for managing connectors
# ============================================

class ShopConnectorRegistryPort(ABC):
    """
    PORT - Registry for managing multiple shop connectors
    
    Allows the system to get the right connector for any platform.
    """
    
    @abstractmethod
    def register(self, platform_code: str, connector_class: type[ShopConnectorPort]) -> None:
        """Register a new connector implementation"""
        pass
    
    @abstractmethod
    def get(self, platform_code: str) -> ShopConnectorPort:
        """Get connector for a specific platform"""
        pass
    
    @abstractmethod
    def list_supported(self) -> List[str]:
        """List all supported platform codes"""
        pass
