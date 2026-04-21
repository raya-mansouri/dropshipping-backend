from typing import Dict, Any


STATUS_MAPPING = {
    "pending": "PENDING",
    "confirmed": "CONFIRMED",
    "processing": "PROCESSING",
    "shipped": "SHIPPED",
    "delivered": "DELIVERED",
    "cancelled": "CANCELLED",
    "returned": "RETURNED",
}


def basalam_order_to_internal(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(payload.get("id")),
        "order_number": payload.get("order_number"),
        "status": STATUS_MAPPING.get(payload.get("status", "").lower(), "PENDING"),
        "customer": {
            "id": str(payload.get("customer", {}).get("id")),
            "name": payload.get("customer", {}).get("name"),
            "phone": payload.get("customer", {}).get("phone"),
        },
        "items": [
            {
                "id": str(item.get("id")),
                "product_id": str(item.get("product_id")),
                "variant_id": str(item.get("variant_id")),
                "title": item.get("title"),
                "quantity": item.get("quantity"),
                "price": item.get("price"),
                "total_price": item.get("total_price"),
            }
            for item in payload.get("items", [])
        ],
        "subtotal": payload.get("subtotal"),
        "shipping_cost": payload.get("shipping_cost"),
        "tax": payload.get("tax"),
        "total": payload.get("total"),
        "shipping_address": payload.get("shipping_address"),
        "billing_address": payload.get("billing_address"),
        "notes": payload.get("notes"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
    }


def internal_status_to_basalam(status: str) -> str:
    reverse_mapping = {v: k for k, v in STATUS_MAPPING.items()}
    return reverse_mapping.get(status.upper(), "pending")
