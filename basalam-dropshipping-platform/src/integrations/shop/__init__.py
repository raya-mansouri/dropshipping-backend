from .connector import (
    BaseShopConnector,
    ConnectionResult,
    Product,
    ProductVariant,
    Inventory,
    Order,
    OrderItem,
)
from .ports import ShopConnectorPort
from .registry import ConnectorRegistry, get_connector, register_connector, registry

# Backward-compatible alias — prefer ShopConnectorPort in new code.
ShopConnector = ShopConnectorPort

__all__ = [
    # Canonical port interface (hexagonal architecture)
    "ShopConnectorPort",
    # Base class with shared implementation utilities
    "BaseShopConnector",
    # Backward-compatible alias — prefer ShopConnectorPort
    "ShopConnector",
    # Data classes
    "ConnectionResult",
    "Product",
    "ProductVariant",
    "Inventory",
    "Order",
    "OrderItem",
    # Registry
    "ConnectorRegistry",
    "get_connector",
    "register_connector",
    "registry",
]
