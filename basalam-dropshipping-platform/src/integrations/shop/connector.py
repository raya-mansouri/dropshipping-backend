from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import structlog

from .ports import ShopConnectorPort

logger = structlog.get_logger(__name__)


@dataclass
class ConnectionResult:
    success: bool
    message: str
    connected_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProductVariant:
    variant_id: str
    sku: Optional[str] = None
    title: Optional[str] = None
    price: Optional[float] = None
    inventory: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Product:
    product_id: str
    title: str
    description: str
    price: float
    category: Optional[Dict[str, Any]] = None
    images: List[str] = field(default_factory=list)
    variants: List[ProductVariant] = field(default_factory=list)
    status: str = "active"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Inventory:
    variant_id: str
    quantity: int
    reserved: int = 0
    available: int = 0
    updated_at: Optional[datetime] = None


@dataclass
class OrderItem:
    item_id: str
    product_id: str
    variant_id: Optional[str] = None
    title: str
    quantity: int
    price: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Order:
    order_id: str
    customer: Dict[str, Any] = field(default_factory=dict)
    items: List[OrderItem] = field(default_factory=list)
    total_price: float = 0.0
    shipping_price: float = 0.0
    status: str = "pending"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WebhookRegistration:
    webhook_id: str
    url: str
    events: List[str]
    created_at: Optional[datetime] = None
    active: bool = True


@dataclass
class ShippingMethod:
    method_id: str
    name: str
    price: float
    estimated_days: Optional[int] = None
    carrier: Optional[str] = None


class BaseShopConnector(ShopConnectorPort):
    """
    Base implementation of ShopConnectorPort with shared functionality.

    Provides shared implementation for connection management,
    pagination, error handling, and common operations.

    Concrete connectors (Basalam, Shopify, WooCommerce) should extend
    this class and implement the remaining abstract methods from
    ShopConnectorPort.
    """

    PLATFORM_CODE: str = ""

    def __init__(self, credentials: Optional[Dict[str, Any]] = None):
        self._credentials = credentials
        self._connected = False
        self._request_timeout = 30.0
        self._max_retries = 3

    @property
    def platform_code(self) -> str:
        return self.PLATFORM_CODE

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def _ensure_connected(self) -> None:
        if not self._connected:
            raise ConnectionError("Not connected to shop")

    async def _handle_request_error(self, error: Exception, context: str) -> None:
        """Handle and log request errors."""
        logger.error("request_error", context=context, error=str(error))
        raise

    async def list_products_paginated(
        self,
        page: int = 1,
        per_page: int = 50,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch products with pagination support.

        Args:
            page: Page number
            per_page: Items per page
            status: Filter by status

        Returns:
            Dict with products and pagination info
        """
        products = await self.fetch_products(page=page, limit=per_page)
        if status:
            products = [p for p in products if p.status == status]

        start = (page - 1) * per_page
        end = start + per_page
        paginated = products[start:end]

        return {
            "products": paginated,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": len(products),
                "pages": (len(products) + per_page - 1) // per_page,
            },
        }

    async def create_order_items(self, items: List[Dict[str, Any]]) -> List[OrderItem]:
        """Convert raw items to OrderItem objects."""
        result = []
        for item in items:
            result.append(
                OrderItem(
                    item_id=item.get("id", ""),
                    product_id=item.get("product_id", ""),
                    variant_id=item.get("variant_id"),
                    title=item.get("title", ""),
                    quantity=item.get("quantity", 1),
                    price=float(item.get("price", 0)),
                    metadata=item.get("metadata", {}),
                )
            )
        return result
