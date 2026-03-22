"""
Domain Model Registry
=====================
Automatically registers all SQLAlchemy domain models with Base.metadata.
Triggered by Python's package import mechanism — runs once when any
src.domains.* module is first imported (e.g., via API routers at startup).

To register a new domain: add one entry to DOMAIN_MODEL_MODULES.
"""
import importlib

DOMAIN_MODEL_MODULES = [
    "src.domains.accounts.models",
    "src.domains.audit_logs.models",
    "src.domains.fraud_detection.models",
    "src.domains.integration_logs.models",
    "src.domains.inventory.models",
    "src.domains.notifications.models",
    "src.domains.orders.models",
    "src.domains.payments.models",
    "src.domains.products.models",
    "src.domains.product_validation.models",
    "src.domains.shops.models",
    "src.domains.system_logs.models",
    "src.domains.webhooks.models",
]

for _module in DOMAIN_MODEL_MODULES:
    importlib.import_module(_module)
