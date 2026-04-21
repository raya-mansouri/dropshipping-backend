# Hexagonal Architecture Implementation

## Overview

This implementation uses **Ports and Adapters (Hexagonal)** pattern to ensure:
1. **Shop Connections**: Easy to add new platforms (Basalam, Shopify, WooCommerce)
2. **Notifications**: Easy to add new channels (SMS, In-App, Webhook)
3. **Testability**: Core domain is isolated from external dependencies

---

## Directory Structure

```
implementation/
├── src/
│   ├── core/
│   │   └── domain/
│   │       └── entity.py          # Base entity with UUID
│   │
│   ├── domains/
│   │   └── shops/
│   │       └── models.py         # SQLAlchemy models
│   │
│   ├── integrations/
│   │   ├── shop/
│   │   │   ├── ports.py          # SHOP CONNECTOR PORT (interface)
│   │   │   └── adapters/
│   │   │       ├── basalam.py    # Basalam adapter
│   │   │       ├── shopify.py    # Future: Shopify adapter
│   │   │       └── woocommerce.py # Future: WooCommerce adapter
│   │   │
│   │   └── notification/
│   │       ├── ports.py          # NOTIFICATION PORT (interface)
│   │       ├── manager.py        # Notification manager
│   │       └── adapters/
│   │           ├── sms.py        # SMS adapter (Kavenegar, Twilio)
│   │           ├── in_app.py    # In-app adapter
│   │           └── webhook.py   # Webhook adapter
│   │
│   └── api/
│       └── v1/
│           └── shops.py          # API endpoints
│
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

---

## Pattern 1: Shop Connectors (Hexagonal)

### Port Interface (src/integrations/shop/ports.py)

```python
class ShopConnectorPort(ABC):
    """Abstract interface for all shop integrations"""
    
    @property
    @abstractmethod
    def platform_code(self) -> str:
        pass
    
    @abstractmethod
    async def connect(self, credentials: ShopCredentials) -> bool:
        pass
    
    @abstractmethod
    async def fetch_products(self, page: int = 1) -> List[ShopProducts]:
        pass
    
    # ... more methods
```

### Adapter Implementation (src/integrations/shop/adapters/basalam.py)

```python
class BasalamConnectorAdapter(ShopConnectorPort):
    """Basalam-specific implementation"""
    
    async def fetch_products(self, page: int = 1) -> List[ShopProducts]:
        # Basalam API calls
        pass
    
    async def fetch_orders(self, since: datetime) -> List[ShopOrder]:
        # Basalam API calls
        pass
```

### Usage

```python
# Get the right connector for any platform
connector = connector_registry.get("basalam")
products = await connector.fetch_products()
```

---

## Pattern 2: Notification Channels (Hexagonal)

### Port Interface (src/integrations/notification/ports.py)

```python
class NotificationPort(ABC):
    """Abstract interface for all notification channels"""
    
    @property
    @abstractmethod
    def channel(self) -> NotificationChannel:
        pass
    
    @abstractmethod
    async def send(self, request: NotificationRequest) -> NotificationResponse:
        pass
```

### Adapters

| Adapter | Channel | Provider |
|---------|---------|----------|
| `NotificationAdapter` | SMTP, SendGrid |
| `KavenegarSMSAdapter` | sms | Kavenegar |
| `TwilioSMSAdapter` | sms | Twilio |
| `InAppNotificationAdapter` | in_app | Database |
| `WebhookNotificationAdapter` | webhook | HTTP POST |

### Usage

```python
# Send notification via specific channel
manager = create_notification_manager(config)
await manager.send(
    channel=NotificationChannel.SMS,
    recipient=NotificationRecipient(phone="09123456789"),
    content=NotificationContent(title="Order", body="New order received")
)

# Or send via event-based template
await manager.notify_event(
    event_type="order_created",
    recipient=NotificationRecipient(user_id=user_id),
    event_data={"order_id": "123", "total": 100000}
)
```

---

## Key Benefits

### 1. Easy to Add New Platforms

```python
# Add Shopify in the future
class ShopifyConnectorAdapter(ShopConnectorPort):
    platform_code = "shopify"
    
    async def fetch_products(self, page: int = 1) -> List[ShopProducts]:
        # Shopify API calls
        pass

# Register it
connector_registry.register("shopify", ShopifyConnectorAdapter)
```

### 2. Easy to Add New Notification Channels

```python
# Add Telegram bot notification
class TelegramNotificationAdapter(NotificationPort):
    channel = NotificationChannel.TELEGRAM
    
    async def send(self, request: NotificationRequest) -> NotificationResponse:
        # Telegram API calls
        pass

# Register it
manager.register_adapter(NotificationChannel.TELEGRAM, TelegramAdapter())
```

### 3. Core Domain is Isolated

- Business logic doesn't know about Basalam API or Kavenegar
- Easy to test with mock adapters
- Can change providers without changing domain code

---

## Database Models

All models use **UUID** as primary key (per a.md requirement):

```python
class Shop(Base):
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # ...

class ShopIntegration(Base):
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    shop_id = Column(PGUUID(as_uuid=True), ForeignKey("shops.id"))
    platform_id = Column(PGUUID(as_uuid=True), ForeignKey("platforms.id"))
    # Unique: (platform_id, external_shop_id)
```

---

## Next Steps

1. **Create database migrations** using Alembic
2. **Implement ShopService** with business logic
3. **Add Shopify/WooCommerce adapters** when needed
4. **Write tests** for adapters and services
