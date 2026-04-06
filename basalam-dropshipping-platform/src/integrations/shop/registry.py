from typing import Dict, Type, List, Optional

from .ports import ShopConnectorPort
from .connectors import BasalamConnector, ShopifyConnector, WooCommerceConnector


class ConnectorRegistry:
    def __init__(self):
        self._connectors: Dict[str, Type[ShopConnectorPort]] = {}
        self._register_default_connectors()

    def _register_default_connectors(self) -> None:
        self.register_connector("basalam", BasalamConnector)
        self.register_connector("shopify", ShopifyConnector)
        self.register_connector("woocommerce", WooCommerceConnector)

    def register_connector(
        self, platform_code: str, connector_class: Type[ShopConnectorPort]
    ) -> None:
        if not issubclass(connector_class, ShopConnectorPort):
            raise TypeError(
                f"{connector_class.__name__} must be a subclass of ShopConnectorPort"
            )
        self._connectors[platform_code.lower()] = connector_class

    def get_connector(
        self, platform_code: str, credentials: Optional[Dict] = None
    ) -> ShopConnectorPort:
        platform = platform_code.lower()
        if platform not in self._connectors:
            supported = ", ".join(self._connectors.keys())
            raise ValueError(
                f"Unknown platform: {platform_code}. Supported: {supported}"
            )

        connector_class = self._connectors[platform]
        return connector_class(credentials=credentials)

    def list_supported(self) -> List[str]:
        return list(self._connectors.keys())

    def is_supported(self, platform_code: str) -> bool:
        return platform_code.lower() in self._connectors


registry = ConnectorRegistry()


def get_connector(
    platform_code: str,
    credentials: Optional[Dict] = None,
    *,
    vendor_id: Optional[str] = None,
) -> ShopConnectorPort:
    connector = registry.get_connector(platform_code, credentials)
    if vendor_id and hasattr(connector, 'set_vendor_id'):
        connector.set_vendor_id(vendor_id)
    return connector


def register_connector(
    platform_code: str, connector_class: Type[ShopConnectorPort]
) -> None:
    registry.register_connector(platform_code, connector_class)
