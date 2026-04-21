class BasalamAPIError(Exception):
    def __init__(self, message: str, code: int = None, response_data: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.response_data = response_data or {}


class AuthenticationError(BasalamAPIError):
    pass


class TokenExpiredError(AuthenticationError):
    pass


class RateLimitError(BasalamAPIError):
    def __init__(self, message: str, retry_after: int = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class NotFoundError(BasalamAPIError):
    pass


class ForbiddenProductError(BasalamAPIError):
    def __init__(
        self, message: str, product_id: str = None, reason: str = None, **kwargs
    ):
        super().__init__(message, **kwargs)
        self.product_id = product_id
        self.reason = reason


class ValidationError(BasalamAPIError):
    pass
