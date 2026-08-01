"""
PURPOSE
-------
HTTP layer for authentication endpoints (signup, login, refresh). Per the
Router -> Service -> Repository -> Model architecture, this file contains
NO business logic: it only parses the request (via Pydantic request
schemas), calls exactly one AuthService method, and returns the result. All
of the actual rules (email uniqueness, password verification, token
validity) live in app.services.auth_service and are never duplicated or
re-checked here.

Exceptions raised by AuthService (EmailAlreadyRegisteredError,
InvalidCredentialsError, InvalidTokenError, UserNotFoundError) are NOT
caught in this file — they propagate up to the global exception handlers
registered in app.core.exceptions (via register_exception_handlers), which
convert them into the standardized {error_code, message} JSON shape. A
router catching and re-wrapping them here would be duplicate, redundant
error handling.
"""
from fastapi import APIRouter, Depends, Request

from app.core.limiter import limiter
from app.dependencies.auth import get_auth_service
from app.schemas.auth import AuthResponse, LoginRequest, RefreshTokenRequest, TokenPair
from app.schemas.user import UserSignupRequest
from app.services.auth_service import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post("/signup", response_model=AuthResponse)
@limiter.limit("5/minute")
async def signup(
    request: Request,
    payload: UserSignupRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    """
    Registers a new user account and immediately returns an authenticated
    session (user profile + a fresh access/refresh token pair) — the
    client does not need to separately call /login after signing up.

    Request validation (email format, password length/complexity, name
    non-blank) happens automatically via the UserSignupRequest schema
    before this function body even runs — a malformed payload never
    reaches AuthService.signup().

    Rate limited to 5 requests/minute per client IP (app.core.limiter),
    the strictest limit of the three auth endpoints — signup is the most
    valuable endpoint to an attacker running automated account-creation
    abuse, so it gets the tightest ceiling.

    `request: Request` is required as the first parameter specifically
    because @limiter.limit(...) needs access to the incoming request to
    determine the caller's IP (via the limiter's key_func) — this is a
    SlowAPI requirement, not something this endpoint uses directly
    itself.

    Raises:
        EmailAlreadyRegisteredError (-> HTTP 409, via the global handler):
            if the email is already registered to an existing account.
        (Pydantic validation errors -> HTTP 422, via the global handler):
            if the payload itself is malformed.
    """
    return await auth_service.signup(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    """
    Authenticates an existing user by email and password, returning
    their profile and a fresh access/refresh token pair.

    Rate limited to 10 requests/minute per client IP — looser than
    signup's 5/minute (legitimate users retry a mistyped password more
    often than they legitimately re-signup), but still strict enough to
    meaningfully slow down credential brute-forcing.

    Raises:
        InvalidCredentialsError (-> HTTP 401, via the global handler):
            if the email doesn't match any account, the password is
            wrong, or the account is inactive. AuthService.login()
            deliberately makes these three cases indistinguishable to
            the caller (see its docstring) — this router does not, and
            must not, add any logic that could re-introduce that
            distinction (e.g. by inspecting which exception subtype was
            raised and varying the response).
    """
    return await auth_service.login(email=payload.email, password=payload.password)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("20/minute")
async def refresh(
    request: Request,
    payload: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPair:
    """
    Exchanges a valid, unexpired refresh token for a brand-new
    access/refresh token pair. Returns TokenPair directly (not wrapped
    in AuthResponse) — unlike signup/login, refresh does not return user
    profile data, since the client already has it from the original
    signup/login call and refreshing tokens doesn't change it.

    Rate limited to 20 requests/minute per client IP — the loosest of
    the three, since this is the endpoint a legitimately-behaving
    frontend calls automatically and relatively frequently (e.g. via a
    silent-refresh interceptor whenever an access token expires), not
    just in response to direct user action.

    Raises:
        InvalidTokenError (-> HTTP 401, via the global handler): if the
            token is malformed, expired, has an invalid signature, or is
            not specifically a refresh-type token.
        UserNotFoundError (-> HTTP 404, via the global handler): if the
            token is otherwise valid but the user id it refers to no
            longer exists or is inactive.
    """
    return await auth_service.refresh_tokens(payload.refresh_token)