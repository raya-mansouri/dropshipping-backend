from typing import Dict, Any, List, Optional


def basalam_product_to_internal(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(payload.get("id")),
        "title": payload.get("title"),
        "description": payload.get("description"),
        "slug": payload.get("slug"),
        "status": payload.get("status"),
        "category_id": payload.get("category_id"),
        "category_name": payload.get("category_name"),
        "brand": payload.get("brand"),
        "tags": payload.get("tags", []),
        "images": [
            {"id": img.get("id"), "url": img.get("url"), "order": img.get("order")}
            for img in payload.get("images", [])
        ],
        "variants": [
            basalam_variant_to_internal(variant)
            for variant in payload.get("variants", [])
        ],
        "price": payload.get("price"),
        "original_price": payload.get("original_price"),
        "discount_percentage": payload.get("discount_percentage"),
        "rating": payload.get("rating"),
        "review_count": payload.get("review_count"),
        "sales_count": payload.get("sales_count"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
    }


def basalam_variant_to_internal(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(payload.get("id")),
        "product_id": str(payload.get("product_id")),
        "sku": payload.get("sku"),
        "title": payload.get("title"),
        "price": payload.get("price"),
        "original_price": payload.get("original_price"),
        "stock": payload.get("stock"),
        "attributes": payload.get("attributes", {}),
        "image_id": payload.get("image_id"),
        "is_active": payload.get("is_active", True),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
    }
