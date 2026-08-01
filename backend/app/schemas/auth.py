"""
PURPOSE
-------
Authentication-flow request/response schemas (Pydantic v2): login,
token refresh, and the combined response returned by signup/login.

User-data shapes (UserSignupRequest, UserPublic) live in
app/schemas/user.py, not here — this file imports UserPublic where it
needs to embed user data in a response, rather than redefining it.
"""
from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserPublic


class LoginRequest(BaseModel):
    """
    Request body for POST /api/v1/auth/login.

    Note the difference from UserSignupRequest's password field: login's
    password has only a loose length bound (1-128), NOT the strength
    rules (uppercase/lowercase/digit) that signup enforces. That's
    deliberate — strength rules belong at the point a password is
    CREATED, not every time it's typed to log in. Applying signup's
    strength validator here would incorrectly reject a legitimate
    login attempt for an existing account whose password was created
    under different (or since-changed) rules, and it would leak
    information about password composition requirements to anyone
    probing the login endpoint.
    """
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshTokenRequest(BaseModel):
    """
    Request body for POST /api/v1/auth/refresh.

    Deliberately a single required string field with no format
    validation beyond "non-empty" — the JWT itself is validated for
    structure, signature, expiry, and type (must be a refresh token, not
    an access token) inside core.security.decode_token(), not here.
    Duplicating JWT-shape validation at the schema layer would be
    redundant with that check and could drift out of sync with it.
    """
    refresh_token: str = Field(min_length=1)


class TokenPair(BaseModel):
    """
    A pair of issued tokens, returned by login/signup (embedded inside
    AuthResponse below) and by the refresh endpoint (returned directly,
    since refresh doesn't need to re-send user data — the client already
    has it from the original login/signup).

    token_type defaults to "bearer" and is included because it's the
    value the client is expected to place in the Authorization header
    ("Authorization: Bearer <access_token>") — spelling this out in the
    response, rather than assuming the client hardcodes "Bearer," keeps
    the contract self-describing.
    """
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    """
    Response body for both POST /auth/signup and POST /auth/login —
    both actions end in the same outcome (an authenticated user with a
    fresh token pair), so they share one response shape rather than two
    near-identical ones.

    Reuses UserPublic from app.schemas.user directly, rather than
    redefining user fields here — this is the "reuse UserPublic where
    appropriate" requirement: AuthResponse doesn't know or care what
    fields UserPublic contains, so if UserPublic's shape ever changes,
    this schema doesn't need to change with it.
    """
    user: UserPublic
    tokens: TokenPair