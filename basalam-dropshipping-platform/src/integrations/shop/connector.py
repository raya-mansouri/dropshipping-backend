from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


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


class ShopConnector(ABC):
    PLATFORM_CODE: str = ""

    def __init__(self, credentials: Optional[Dict[str, Any]] = None):
        self._credentials = credentials
        self._connected = False
        self._connection_result: Optional[ConnectionResult] = None

    @property
    def platform_code(self) -> str:
        return self.PLATFORM_CODE

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def connection_result(self) -> Optional[ConnectionResult]:
        return self._connection_result

    @abstractmethod
    async def connect(self, credentials: Dict[str, Any]) -> ConnectionResult:
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        pass

    @abstractmethod
    async def get_products(self) -> List[Product]:
        pass

    @abstractmethod
    async def get_product(self, product_id: str) -> Product:
        pass

    @abstractmethod
    async def get_inventory(self, variant_id: str) -> Inventory:
        pass

    @abstractmethod
    async def update_inventory(self, variant_id: str, quantity: int) -> Inventory:
        pass

    @abstractmethod
    async def get_orders(self) -> List[Order]:
        pass

    @abstractmethod
    async def get_order(self, order_id: str) -> Order:
        pass

    @abstractmethod
    async def register_webhook(self, url: str, events: List[str]) -> str:
        pass

    @abstractmethod
    async def delete_webhook(self, webhook_id: str) -> bool:
        pass

    async def _ensure_connected(self) -> None:
        if not self._connected:
            raise ConnectionError("Not connected to shop")
