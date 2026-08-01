"""
PURPOSE
-------
HTTP layer for the authenticated user's own profile. Milestone 1 exposes
exactly one endpoint here: GET /me. No business logic lives in this file —
authentication and user resolution are entirely delegated to
get_current_user (app.dependencies.auth), and this router does nothing but
shape that result into the UserPublic response contract.
"""
from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_user
from app.schemas.user import UserPublic

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get("/me", response_model=UserPublic)
async def get_me(current_user=Depends(get_current_user)) -> UserPublic:
    """
    Returns the profile of the currently authenticated user.

    Authentication is handled entirely by the get_current_user dependency
    (app.dependencies.auth): it extracts the bearer token from the
    Authorization header, validates it, and resolves it to a user record
    — or raises InvalidTokenError / UserNotFoundError before this
    function body ever runs, if authentication fails for any reason. By
    the time this endpoint executes, current_user is guaranteed to be a
    real, active, authenticated user.

    This endpoint does not query UserRepository directly, does not
    instantiate AuthService, and does not evaluate any rule — it maps
    the already-resolved current_user onto the UserPublic response
    contract and returns it. That mapping is deliberately explicit
    (rather than returning current_user as-is and relying solely on
    response_model to filter out fields like password_hash) so that
    what leaves this endpoint is visibly, auditably safe, not merely
    safe because a framework feature happened to strip it.

    Args:
        current_user: injected by get_current_user; the authenticated
            user resolved from the request's access token.

    Returns:
        UserPublic: the authenticated user's public profile
            (id, email, full_name, created_at) — never password_hash.

    Raises:
        InvalidTokenError (-> HTTP 401, via the global handler): if the
            Authorization header is missing or the access token is
            malformed, expired, or invalid — raised by get_current_user
            before this function runs.
        UserNotFoundError (-> HTTP 404, via the global handler): if the
            token is valid but the account it refers to no longer exists
            or is inactive — also raised by get_current_user before this
            function runs.
    """
    return UserPublic(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        created_at=current_user.created_at,
    )