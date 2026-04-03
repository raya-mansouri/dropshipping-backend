from typing import Optional, Dict, Any, List

import httpx

from src.core.config import get_settings

from .exceptions import (
    BasalamAPIError,
    AuthenticationError,
    TokenExpiredError,
    RateLimitError,
    NotFoundError,
    ForbiddenProductError,
    ValidationError,
)
from .retry import BasalamRetryPolicy
from .rate_limiter import RateLimiter
from .mappers import (
    basalam_product_to_internal,
    basalam_variant_to_internal,
    basalam_order_to_internal,
    internal_status_to_basalam,
)


class BasalamClient:
    BASE_URL = get_settings().basalam_api_url

    DEFAULT_POOL_LIMITS = httpx.Limits(
        max_keepalive_connections=20,
        max_connections=100,
        keepalive_expiry=30.0,
    )

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        pool_limits: Optional[httpx.Limits] = None,
        pool_timeout: float = 30.0,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self._http_client: Optional[httpx.AsyncClient] = None
        self.retry_policy = BasalamRetryPolicy(self)
        self.rate_limiter: Optional[RateLimiter] = None
        self._pool_limits = pool_limits or self.DEFAULT_POOL_LIMITS
        self._pool_timeout = pool_timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            headers = {}
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            self._http_client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=headers,
                timeout=httpx.Timeout(self._pool_timeout, pool=self._pool_timeout),
                limits=self._pool_limits,
            )
        return self._http_client

    async def close(self):
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    def _handle_response_error(self, response: httpx.Response):
        status = response.status_code
        try:
            data = response.json()
            message = data.get("message", data.get("error", "Unknown error"))
            code = data.get("code")
        except Exception:
            message = response.text or "Unknown error"
            data = {}
            code = status

        if status == 401:
            if "token" in message.lower() or "expired" in message.lower():
                raise TokenExpiredError(message, code=code, response_data=data)
            raise AuthenticationError(message, code=code, response_data=data)
        elif status == 403:
            if "product" in message.lower():
                raise ForbiddenProductError(
                    message,
                    product_id=data.get("product_id"),
                    reason=data.get("reason"),
                    code=code,
                    response_data=data,
                )
            raise BasalamAPIError(message, code=code, response_data=data)
        elif status == 404:
            raise NotFoundError(message, code=code, response_data=data)
        elif status == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                message,
                retry_after=int(retry_after) if retry_after else None,
                code=code,
                response_data=data,
            )
        elif status == 422:
            raise ValidationError(message, code=code, response_data=data)
        elif status >= 500:
            raise BasalamAPIError(message, code=code, response_data=data)
        else:
            raise BasalamAPIError(message, code=code, response_data=data)

    async def _request(
        self,
        method: str,
        endpoint: str,
        rate_limit_endpoint: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if self.rate_limiter and rate_limit_endpoint:
            await self.rate_limiter.wait_if_needed(rate_limit_endpoint)

        client = await self._get_client()
        response = await client.request(method, endpoint, **kwargs)

        if response.status_code >= 400:
            self._handle_response_error(response)

        return response.json()

    async def get_access_token(self) -> Dict[str, str]:
        settings = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.basalam_auth_url}/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )

        if response.status_code >= 400:
            self._handle_response_error(response)

        data = response.json()
        self.access_token = data.get("access_token")
        self.refresh_token = data.get("refresh_token")

        if self._http_client:
            self._http_client.headers["Authorization"] = f"Bearer {self.access_token}"

        return data

    async def refresh_access_token(self) -> Dict[str, str]:
        if not self.refresh_token:
            raise AuthenticationError("No refresh token available")

        settings = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.basalam_auth_url}/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )

        if response.status_code >= 400:
            self._handle_response_error(response)

        data = response.json()
        self.access_token = data.get("access_token")
        self.refresh_token = data.get("refresh_token")

        if self._http_client:
            self._http_client.headers["Authorization"] = f"Bearer {self.access_token}"

        return data

    # ------------------------------------------------------------------
    # OAuth 2.0 — Authorization Code Flow
    # ------------------------------------------------------------------

    async def exchange_authorization_code(
        self, code: str, redirect_uri: str
    ) -> Dict[str, Any]:
        """Exchange an OAuth authorization code for access/refresh tokens.

        POSTs to the Basalam auth server with grant_type=authorization_code.
        """
        settings = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.basalam_auth_url}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )

        if response.status_code >= 400:
            self._handle_response_error(response)

        data = response.json()
        self.access_token = data.get("access_token")
        self.refresh_token = data.get("refresh_token")

        if self._http_client:
            self._http_client.headers["Authorization"] = f"Bearer {self.access_token}"

        return data

    async def refresh_access_token_with_code(
        self, refresh_token: str
    ) -> Dict[str, Any]:
        """Refresh an access token using a refresh token.

        POSTs to the Basalam auth server with grant_type=refresh_token.
        """
        settings = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.basalam_auth_url}/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )

        if response.status_code >= 400:
            self._handle_response_error(response)

        data = response.json()
        self.access_token = data.get("access_token")
        self.refresh_token = data.get("refresh_token")

        if self._http_client:
            self._http_client.headers["Authorization"] = f"Bearer {self.access_token}"

        return data

    async def get_current_user(self, access_token: Optional[str] = None) -> Dict[str, Any]:
        """Fetch current authenticated user info including vendor details.

        GETs /users/me and returns {id, vendor: {id, title}}.
        """
        token = access_token or self.access_token
        if not token:
            raise AuthenticationError("No access token available")

        settings = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.basalam_api_url}/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )

        if response.status_code >= 400:
            self._handle_response_error(response)

        return response.json()

    async def list_products(
        self, vendor_id: Optional[str] = None, page: int = 1, per_page: int = 20
    ) -> Dict[str, Any]:
        async def _fetch():
            endpoint = (
                f"/vendors/{vendor_id}/products" if vendor_id else "/products"
            )
            return await self._request(
                "GET",
                endpoint,
                rate_limit_endpoint="products",
                params={"page": page, "per_page": per_page},
            )

        response = await self.retry_policy.execute(_fetch)
        return {
            "products": [
                basalam_product_to_internal(p) for p in response.get("data", [])
            ],
            "pagination": response.get("pagination", {}),
        }

    async def get_product(self, product_id: str) -> Dict[str, Any]:
        async def _fetch():
            return await self._request(
                "GET",
                f"/products/{product_id}",
                rate_limit_endpoint="products",
            )

        response = await self.retry_policy.execute(_fetch)
        return basalam_product_to_internal(response.get("data", {}))

    async def search_products(
        self, query: str, category_id: Optional[str] = None
    ) -> Dict[str, Any]:
        async def _fetch():
            params = {"q": query}
            if category_id:
                params["category_id"] = category_id
            return await self._request(
                "GET",
                "/products/search",
                rate_limit_endpoint="products",
                params=params,
            )

        response = await self.retry_policy.execute(_fetch)
        return {
            "products": [
                basalam_product_to_internal(p) for p in response.get("data", [])
            ],
            "pagination": response.get("pagination", {}),
        }

    async def list_orders(
        self, status: Optional[str] = None, page: int = 1
    ) -> Dict[str, Any]:
        async def _fetch():
            params = {"page": page}
            if status:
                params["status"] = status
            return await self._request(
                "GET",
                "/orders",
                rate_limit_endpoint="orders",
                params=params,
            )

        response = await self.retry_policy.execute(_fetch)
        return {
            "orders": [basalam_order_to_internal(o) for o in response.get("data", [])],
            "pagination": response.get("pagination", {}),
        }

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        async def _fetch():
            return await self._request(
                "GET",
                f"/orders/{order_id}",
                rate_limit_endpoint="orders",
            )

        response = await self.retry_policy.execute(_fetch)
        return basalam_order_to_internal(response.get("data", {}))

    async def update_order_status(self, order_id: str, status: str) -> Dict[str, Any]:
        async def _fetch():
            return await self._request(
                "PATCH",
                f"/orders/{order_id}/status",
                rate_limit_endpoint="orders",
                json={"status": internal_status_to_basalam(status)},
            )

        response = await self.retry_policy.execute(_fetch)
        return basalam_order_to_internal(response.get("data", {}))

    async def get_inventory(self, product_id: str) -> Dict[str, Any]:
        async def _fetch():
            return await self._request(
                "GET",
                f"/products/{product_id}/inventory",
                rate_limit_endpoint="inventory",
            )

        response = await self.retry_policy.execute(_fetch)
        return {
            "product_id": product_id,
            "variants": [
                {
                    "variant_id": v.get("variant_id"),
                    "sku": v.get("sku"),
                    "stock": v.get("stock"),
                    "reserved": v.get("reserved"),
                    "available": v.get("available"),
                }
                for v in response.get("data", {}).get("variants", [])
            ],
        }

    async def update_inventory(self, variant_id: str, quantity: int) -> Dict[str, Any]:
        async def _fetch():
            return await self._request(
                "PUT",
                f"/variants/{variant_id}/inventory",
                rate_limit_endpoint="inventory",
                json={"quantity": quantity},
            )

        response = await self.retry_policy.execute(_fetch)
        return {
            "variant_id": variant_id,
            "quantity": response.get("data", {}).get("quantity"),
            "updated_at": response.get("data", {}).get("updated_at"),
        }

    async def register_webhook(self, url: str, events: List[str]) -> Dict[str, Any]:
        settings = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.basalam_webhook_url}/webhooks",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={
                    "event_ids": events,
                    "request_method": "POST",
                    "url": url,
                    "is_active": True,
                    "register_me": True,
                },
            )

        if response.status_code >= 400:
            self._handle_response_error(response)

        return response.json()

    async def subscribe_user_to_webhook(
        self, webhook_id: str, access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Subscribe the vendor to a webhook so their events flow to it."""
        token = access_token or self.access_token
        settings = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.basalam_webhook_url}/webhooks/{webhook_id}/subscribe",
                headers={"Authorization": f"Bearer {token}"},
            )

        if response.status_code >= 400:
            self._handle_response_error(response)

        return response.json()

    async def list_webhooks(self) -> Dict[str, Any]:
        settings = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.basalam_webhook_url}/webhooks",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )

        if response.status_code >= 400:
            self._handle_response_error(response)

        return {"webhooks": response.json().get("data", [])}

    async def delete_webhook(self, webhook_id: str) -> Dict[str, Any]:
        settings = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{settings.basalam_webhook_url}/webhooks/{webhook_id}",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )

        if response.status_code >= 400:
            self._handle_response_error(response)

        return response.json()
