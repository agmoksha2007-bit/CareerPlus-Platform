"""
PURPOSE
-------
Security primitives for the authentication foundation: password hashing
(bcrypt via passlib) and JWT issuing/verification (python-jose).

This module deliberately contains NO business logic (no "does this email
already exist" type checks) — it only knows how to hash/verify a password
and how to create/decode a token. AuthService (a later step) composes these
primitives into actual signup/login/refresh flows.
"""
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# --------------------------------------------------------------------
# Password hashing context.
#
# schemes=["bcrypt"]: bcrypt is the production-standard choice for
# password hashing — it's deliberately slow (adjustable work factor),
# which is exactly what you want for password hashing (resists brute
# force) and exactly what you don't want for anything performance
# sensitive. Never use a fast general-purpose hash (MD5, SHA-256 alone)
# for passwords.
#
# deprecated="auto": if a second scheme is ever added later (e.g.
# migrating to argon2), passlib will automatically flag hashes using the
# older scheme as "needs rehash" on next successful login, enabling a
# transparent migration path without forcing a password reset.
# --------------------------------------------------------------------
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(str, Enum):
    """
    Distinguishes access tokens from refresh tokens inside the JWT
    payload itself (the `type` claim below). This is what makes it
    impossible to use a stolen access token to hit the refresh endpoint,
    or vice versa — decode_token() rejects a token whose `type` claim
    doesn't match what the caller expects.
    """
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    """
    Hashes a plaintext password using bcrypt.

    Called exactly once, at signup, before the password ever touches the
    database. The plaintext password itself is never logged, stored, or
    passed beyond this function call and the signup form submission.
    """
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Checks a plaintext password (typed at login) against a stored bcrypt
    hash. Returns True/False — never raises on a wrong password, so
    calling code (AuthService.login) can treat "wrong password" as an
    ordinary business-rule failure, not an exception to catch.

    bcrypt.verify is timing-safe by construction (constant-time
    comparison internally), which matters for password-checking code:
    a naive `==` string comparison can leak information about how many
    characters matched via response-time differences.
    """
    return _pwd_context.verify(plain_password, hashed_password)


def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta) -> str:
    """
    Internal helper shared by create_access_token and create_refresh_token
    — both tokens have identical structure (subject, type, issued-at,
    expiry), differing only in which TokenType and how long until expiry.
    Not exported (leading underscore): callers always go through the two
    public functions below, which pick the correct expiry from settings
    for each token type. This avoids a caller accidentally passing the
    wrong expiry for the wrong token type.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,              # "subject" — standard JWT claim, holds the user's id
        "type": token_type.value,    # custom claim: "access" or "refresh"
        "iat": now,                  # "issued at" — standard claim, supports auditing/debugging
        "exp": now + expires_delta,  # "expiry" — standard claim; jose enforces this automatically
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str) -> str:
    """
    Issues a short-lived access token (default 15 minutes, from
    settings.ACCESS_TOKEN_EXPIRE_MINUTES). Sent as `Authorization: Bearer
    <token>` on every authenticated request. Short-lived by design: if
    one is ever stolen (e.g. via a compromised client), the exposure
    window is small.
    """
    return _create_token(
        user_id,
        TokenType.ACCESS,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: str) -> str:
    """
    Issues a long-lived refresh token (default 7 days, from
    settings.REFRESH_TOKEN_EXPIRE_DAYS). Used ONLY against the
    /auth/refresh endpoint to obtain a new access token — never sent as
    an Authorization header on ordinary API requests. This separation is
    what limits the blast radius of a stolen access token: it cannot be
    used to mint further tokens.
    """
    return _create_token(
        user_id,
        TokenType.REFRESH,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType) -> str:
    """
    Decodes and validates a JWT, returning the subject (user id) encoded
    inside it.

    Three independent checks happen here, and any failure raises
    JWTError (caught by the caller — AuthService or the get_current_user
    dependency, both built in later steps):

    1. Signature + expiry validation — jwt.decode() itself raises
       JWTError if the signature doesn't match settings.JWT_SECRET_KEY,
       or if the token's `exp` claim is in the past. This is python-jose
       enforcing standard JWT semantics automatically.
    2. Type check — rejects a token whose `type` claim doesn't match
       `expected_type`. This is the check that prevents a refresh token
       being replayed as an access token (or vice versa): each call site
       passes the ONE type it's willing to accept.
    3. Subject presence — a token that somehow has no `sub` claim is
       treated as invalid rather than returning None and letting a
       caller silently look up "no user."

    Raising JWTError (rather than returning None/False) is deliberate:
    it forces every caller to explicitly handle the invalid-token case
    (via try/except), rather than allowing a forgotten None-check to
    silently let an invalid token through.
    """
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

    if payload.get("type") != expected_type.value:
        raise JWTError(
            f"Expected token type '{expected_type.value}', got '{payload.get('type')}'"
        )

    subject: str | None = payload.get("sub")
    if subject is None:
        raise JWTError("Token missing subject")

    return subject