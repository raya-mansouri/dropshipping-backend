from typing import Dict, Any, List, Optional


def basalam_product_to_internal(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map real Basalam product to internal format.

    Real Basalam product shape:
    - id (not product_id)
    - photo{original, id} (not images[])
    - status{value} (numeric, 2976=active)
    - inventory (top-level)
    - is_wholesale
    """
    # Handle status: Basalam returns {value: 2976, name: "active"} or numeric
    status_field = payload.get("status", {})
    if isinstance(status_field, dict):
        status_value = status_field.get("value")
        status = "active" if status_value == 2976 else str(status_value)
    else:
        status = str(status_field) if status_field else "active"

    # Handle photo: Basalam returns {original: url, id: int}
    photo = payload.get("photo", {})
    media = []
    if photo:
        media.append({
            "id": photo.get("id"),
            "url": photo.get("original", ""),
            "order": 0,
        })

    return {
        "id": str(payload.get("id")),
        "title": payload.get("title"),
        "description": payload.get("description"),
        "slug": payload.get("slug"),
        "status": status,
        "category_id": payload.get("category_id"),
        "category_name": payload.get("category_name"),
        "brand": payload.get("brand"),
        "tags": payload.get("tags", []),
        "images": media,
        "variants": [
            basalam_variant_to_internal(variant)
            for variant in payload.get("variants", [])
        ],
        "price": payload.get("price"),
        "original_price": payload.get("original_price"),
        "discount_percentage": payload.get("discount_percentage"),
        "inventory": payload.get("inventory", 0),
        "is_wholesale": payload.get("is_wholesale", False),
        "rating": payload.get("rating"),
        "review_count": payload.get("review_count"),
        "sales_count": payload.get("sales_count"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
    }


def basalam_variant_to_internal(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map real Basalam variant to internal format.

    Real variant shape from Basalam may have different field names.
    """
    return {
        "id": str(payload.get("id")),
        "product_id": str(payload.get("product_id", payload.get("product", ""))),
        "sku": payload.get("sku"),
        "title": payload.get("title"),
        "price": payload.get("price"),
        "original_price": payload.get("original_price"),
        "stock": payload.get("stock", payload.get("inventory", 0)),
        "attributes": payload.get("attributes", {}),
        "image_id": payload.get("image_id"),
        "is_active": payload.get("is_active", True),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
    }


# Reverse mapping: internal status → Basalam status code
_STATUS_TO_BASALAM = {
    "active": 2976,
    "inactive": 0,
    "draft": 0,
}


def internal_status_to_basalam(status: str) -> int:
    """Convert internal status string to Basalam numeric status code."""
    return _STATUS_TO_BASALAM.get(status, 0)
