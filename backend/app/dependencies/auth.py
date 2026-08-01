"""
PURPOSE
-------
FastAPI dependency-injection wiring for authentication. This is the layer
that turns "a request came in with an Authorization header" into "here is
the fully validated, loaded User" — routers (a later step) depend on
get_current_user() and never touch token extraction, decoding, or
repository lookups themselves.

Centralizing Depends(...) providers here also means this is the ONE place
to substitute a fake UserRepository/AuthService in tests, without touching
any router code.
"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.exceptions import InvalidTokenError, UserNotFoundError
from app.core.security import TokenType, decode_token
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService

# HTTPBearer, not OAuth2PasswordBearer: this app has no OAuth2
# password-flow endpoint (our login takes a JSON body via LoginRequest,
# not an OAuth2 form). HTTPBearer does exactly what's needed here — parse
# "Authorization: Bearer <token>" and hand back the raw credential string
# — without implying an OAuth2 flow that doesn't exist.
#
# auto_error=False: if the header is missing entirely, HTTPBearer will
# return None instead of raising its own generic 403 immediately. This
# lets get_current_user() below raise OUR InvalidTokenError with a
# consistent {error_code, message} shape (via the exception handler built
# in core/exceptions.py), rather than FastAPI's default "Not
# authenticated" HTTPException, keeping every auth failure on this
# platform structured the same way.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_user_repository() -> UserRepository:
    """
    Provides a UserRepository instance. Trivial today (no constructor
    arguments), but declaring it as a dependency provider — rather than
    routers/services instantiating UserRepository() directly — is what
    makes it possible to override this with a fake/mock repository in
    tests via FastAPI's dependency_overrides, without changing any
    router or service code.
    """
    return UserRepository()


def get_auth_service(
    user_repository: UserRepository = Depends(get_user_repository),
) -> AuthService:
    """
    Provides an AuthService instance, wired to the repository from
    get_user_repository() above. Routers depend on THIS, never construct
    AuthService(...) themselves — same override-ability reasoning as
    get_user_repository().
    """
    return AuthService(user_repository)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    user_repository: UserRepository = Depends(get_user_repository),
):
    """
    Resolves the authenticated User from the request's Authorization
    header. This is the dependency every protected router endpoint will
    declare (e.g. `current_user = Depends(get_current_user)`) to require
    authentication.

    No return-type annotation is declared here on purpose: annotating
    `-> User` would require importing app.models.User into the
    dependencies layer purely for typing, which is a coupling this file
    doesn't otherwise need — every actual operation here goes through
    user_repository, never the model directly. FastAPI does not require
    a return-type annotation on a Depends(...) provider (unlike a path
    operation's return type, which FastAPI DOES inspect for automatic
    response_model inference) — so this has no effect on runtime
    behavior. The concrete return type is whatever UserRepository.get_by_id
    returns.

    Steps, in order:

    1. Extract the token. `credentials` is None if the Authorization
       header was missing entirely (because _bearer_scheme was built
       with auto_error=False) — treated as InvalidTokenError, same as
       any other auth failure, rather than a special "missing" case.
       When present, `credentials.credentials` is the raw token string
       (HTTPBearer has already stripped the literal "Bearer " prefix).

    2. Decode + validate the token via core.security.decode_token(),
       with expected_type=TokenType.ACCESS. This single call verifies
       the signature, checks expiry, AND confirms this is specifically
       an access token — a well-formed, unexpired REFRESH token
       presented here is correctly rejected, because refresh tokens must
       only ever be used against the /auth/refresh endpoint, never as a
       bearer credential on ordinary requests. Any failure from
       decode_token() (a jose.JWTError) is caught and re-raised as
       InvalidTokenError, so this dependency — like AuthService — never
       leaks a raw jose exception type to its caller.

    3. Load the user via the repository, using the user id decoded from
       the token's `sub` claim. If no such user exists, OR the account
       is inactive (soft-disabled per the architecture doc), this
       raises UserNotFoundError — distinct from InvalidTokenError,
       because the token itself was perfectly valid; what's missing or
       no-longer-usable is the account it refers to. This is the same
       distinction AuthService.refresh_tokens() makes, applied here to
       every authenticated request rather than just token refresh.

    Args:
        credentials: extracted by FastAPI from the Authorization header
            via the HTTPBearer scheme; None if the header was absent.
        user_repository: injected via get_user_repository() above.

    Returns:
        The authenticated, active user document, as returned by
        UserRepository.get_by_id().

    Raises:
        InvalidTokenError: if the Authorization header is missing, or
            the token is malformed, expired, has an invalid signature,
            or is not specifically an access-type token.
        UserNotFoundError: if the token is otherwise valid but the user
            id it refers to no longer exists or is inactive.
    """
    if credentials is None:
        raise InvalidTokenError("Not authenticated")

    try:
        user_id = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except JWTError as exc:
        raise InvalidTokenError("Access token is invalid or expired") from exc

    user = await user_repository.get_by_id(user_id)
    if user is None or not user.is_active:
        raise UserNotFoundError("The account associated with this token no longer exists")

    return user