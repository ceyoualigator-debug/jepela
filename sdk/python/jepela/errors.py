"""One error class per answer the gateway can give, so code can catch what it can handle."""
from __future__ import annotations


class JepelaError(Exception):
    """Base class. `status` is the HTTP status, `kind` the gateway's error type, `retry_after` seconds when given."""

    def __init__(self, message: str, status: int | None = None, kind: str | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status, self.kind, self.retry_after = status, kind, retry_after


class AuthenticationError(JepelaError):     # 401
    pass


class PaymentRequiredError(JepelaError):    # 402: no credit left
    pass


class PermissionDeniedError(JepelaError):   # 403: for example sign-up is off, or an invite code is needed
    pass


class NotFoundError(JepelaError):           # 404
    pass


class ConflictError(JepelaError):           # 409: a limit such as the number of golden cases
    pass


class BadRequestError(JepelaError):         # 413, 415, 422
    pass


class RateLimitError(JepelaError):          # 429
    pass


class ServerError(JepelaError):             # 500
    pass


class EngineError(JepelaError):             # 502, 503: the engine or the product behind the gateway
    pass


class ConnectionFailed(JepelaError):        # no HTTP answer at all
    pass


BY_STATUS = {401: AuthenticationError, 402: PaymentRequiredError, 403: PermissionDeniedError, 404: NotFoundError, 409: ConflictError, 413: BadRequestError, 415: BadRequestError,
             422: BadRequestError, 429: RateLimitError, 500: ServerError, 502: EngineError, 503: EngineError}


def error_for(status: int, message: str, kind: str | None = None, retry_after: float | None = None) -> JepelaError:
    return BY_STATUS.get(status, JepelaError)(message, status=status, kind=kind, retry_after=retry_after)
