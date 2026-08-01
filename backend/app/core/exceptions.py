"""
PURPOSE
-------
Domain-level exception hierarchy AND the FastAPI exception handlers that
translate those exceptions (plus validation errors and unexpected 500s)
into one consistent JSON error shape: {"error_code": str, "message": str}.

Services raise AppError subclasses instead of HTTPException directly — this
keeps business logic framework-agnostic (a service shouldn't need to know
it's being called over HTTP) and means the frontend only ever has to parse
ONE error response shape, regardless of which module or failure produced
it.

register_exception_handlers(app) is called once from main.py during app
setup (a later step) — this file does not import or construct the FastAPI
app itself, only the handler functions and the registration entrypoint.
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("careerpulse")


# ======================================================================
# Domain exception hierarchy
# ======================================================================

class AppError(Exception):
    """
    Base class for every expected, handled application error.

    Each subclass declares its own status_code and error_code. Services
    raise these directly (e.g. `raise InvalidCredentialsError("...")`) —
    they never construct an HTTPException or a JSONResponse themselves;
    that translation happens in exactly one place, the handler below.
    """
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class EmailAlreadyRegisteredError(AppError):
    """Raised by AuthService.signup() when the email is already in use."""
    status_code = status.HTTP_409_CONFLICT
    error_code = "email_already_registered"


class InvalidCredentialsError(AppError):
    """
    Raised by AuthService.login() for both 'no such user' and 'wrong
    password' — deliberately the same exception/message for both cases,
    to avoid leaking which registered emails exist (email enumeration).
    """
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "invalid_credentials"


class InvalidTokenError(AppError):
    """
    Raised when a JWT (access or refresh) is missing, expired, malformed,
    or of the wrong type for the endpoint that received it.
    """
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "invalid_token"


class UserNotFoundError(AppError):
    """
    Raised when a user id decoded from a valid token no longer resolves
    to an existing user (e.g. the account was deleted after the token
    was issued but before it expired).
    """
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "user_not_found"


# ======================================================================
# Exception handlers
# ======================================================================

async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """
    Handles every AppError subclass raised anywhere in the app. This is
    the ONLY place that constructs the {"error_code", "message"} response
    body — no router or service builds this shape by hand, which is what
    keeps every error response on the platform identically structured.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "message": exc.message},
    )


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handles Pydantic/FastAPI request validation failures (malformed
    input — e.g. signup payload missing a required field, or a weak
    password rejected by a field_validator). These are distinct from
    AppError: validation failures mean "the request itself was
    malformed," not "the request was well-formed but the action isn't
    allowed" — the frontend can and should treat these differently
    (e.g. highlight a specific form field vs. show a generic error).

    Normalized into the same {"error_code", "message"} shape for
    consistency, with the field-level detail preserved under "errors" so
    the frontend CAN use it for field-specific messages if it chooses to,
    without being required to.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "validation_error",
            "message": "One or more fields failed validation.",
            "errors": exc.errors(),
        },
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all for anything that is NOT an AppError or a validation error
    — i.e. a genuine bug or an unexpected failure (a database timeout, a
    programming error). Two things matter here for production quality:

    1. The full exception is logged server-side (via logger.exception,
       which includes the stack trace) so it's debuggable.
    2. The response sent to the CLIENT never includes exception details,
       stack traces, or internal messages — only a generic message and a
       stable error_code. Leaking internal error text (file paths,
       library names, query fragments) to an API client is an
       information-disclosure risk.
    """
    logger.exception("Unhandled exception processing request: %s %s", request.method, request.url)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": "internal_error",
            "message": "Something went wrong on our end. Please try again.",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Registers all three handlers above on the given FastAPI app instance.
    Called once from main.py during app setup — main.py does:

        from app.core.exceptions import register_exception_handlers
        register_exception_handlers(app)

    Order doesn't matter for exception_handler registration (FastAPI
    matches by exception type, most-specific first), but they're grouped
    here for readability: domain errors, then validation errors, then
    the unhandled-exception catch-all.
    """
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)