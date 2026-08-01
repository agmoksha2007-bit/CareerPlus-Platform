"""
PURPOSE
-------
Authentication business logic: signup, login, and token refresh. This is
the layer that enforces the RULES (e.g. "an email can only be registered
once," "wrong password and no-such-user produce an identical error to
prevent email enumeration"), as opposed to core.security (which only knows
how to hash/verify/encode/decode, with no opinion on what those operations
MEAN for the application) and UserRepository (which only knows how to
read/write User documents, with no opinion on what's ALLOWED).

Per the Router -> Service -> Repository -> Model architecture, this file:
- depends on UserRepository for all database access — it never imports or
  touches app.models.User directly.
- is framework-agnostic — nothing here knows FastAPI exists. Routers (a
  later step) translate between HTTP and these method calls; this class
  could be unit-tested with zero HTTP machinery involved.
"""
from jose import JWTError

from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserNotFoundError,
)
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AuthResponse, TokenPair
from app.schemas.user import UserPublic


class AuthService:
    """
    Orchestrates UserRepository + core.security to implement signup,
    login, and refresh. Holds no state of its own beyond the repository
    it's constructed with — a fresh AuthService(user_repository) is cheap
    to create per-request (this is what the DI wiring in a later step
    will do).
    """

    def __init__(self, user_repository: UserRepository):
        self._users = user_repository

    async def signup(self, email: str, password: str, full_name: str) -> AuthResponse:
        """
        Registers a new user and immediately logs them in.

        Business rules enforced here, in order:
        1. Email uniqueness — looks up the email via the repository
           first. If a user with this email already exists,
           EmailAlreadyRegisteredError is raised and NOTHING is created
           or hashed. This check-then-create isn't perfectly race-proof
           on its own (two simultaneous signups with the same email
           could both pass this check before either inserts) — the
           actual, unconditional guarantee against duplicate accounts is
           the unique index on User.email (architecture doc Section
           4.1), enforced by MongoDB itself. This application-level
           check exists purely to produce a clean 409
           EmailAlreadyRegisteredError instead of a raw database
           duplicate-key exception surfacing to the caller.
        2. Password hashing — the plaintext password is hashed via
           core.security.hash_password() BEFORE it's handed to the
           repository. AuthService is the only layer that ever sees the
           plaintext password; UserRepository.create() only ever
           receives a hash.
        3. User creation — delegated entirely to UserRepository.create().
        4. Token issuance — a fresh access/refresh token pair is created
           for the new user, so signup doubles as an immediate login
           (no separate "log in after signing up" step required from the
           client).

        Returns:
            AuthResponse containing the new user's public profile and a
            fresh token pair.

        Raises:
            EmailAlreadyRegisteredError: if the email is already
                registered to an existing account.
        """
        existing_user = await self._users.get_by_email(email)
        if existing_user is not None:
            raise EmailAlreadyRegisteredError("An account with this email already exists")

        password_hash = hash_password(password)
        user = await self._users.create(email=email, password_hash=password_hash, full_name=full_name)

        return AuthResponse(
            user=self._to_user_public(user),
            tokens=self._issue_token_pair(str(user.id)),
        )

    async def login(self, email: str, password: str) -> AuthResponse:
        """
        Authenticates an existing user by email + password.

        Business rules enforced here:
        1. Identical failure for "no such user" and "wrong password" —
           both cases raise the exact same InvalidCredentialsError with
           the exact same message. This is deliberate: if "no such user"
           and "wrong password" produced DIFFERENT errors, an attacker
           could use the login endpoint to enumerate which emails are
           registered on the platform (submit an email, see whether the
           error says "no account" vs. "wrong password"). Collapsing
           both into one outcome closes that channel.
        2. Inactive accounts are rejected the same way — a deactivated
           user (User.is_active == False, per the architecture doc's
           soft-disable design) cannot log in, and again produces the
           SAME InvalidCredentialsError rather than a distinct "account
           disabled" message, for the same enumeration-prevention
           reasoning: telling an unauthenticated caller "this specific
           account is disabled" is itself information disclosure.
        3. On success, a fresh token pair is issued — login always
           produces NEW tokens; it never reuses or extends any
           previously-issued token.

        Returns:
            AuthResponse containing the authenticated user's public
            profile and a fresh token pair.

        Raises:
            InvalidCredentialsError: if the email doesn't match any
                account, the password is wrong, or the account is
                inactive. The three cases are indistinguishable to the
                caller by design.
        """
        user = await self._users.get_by_email(email)

        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Incorrect email or password")

        if not user.is_active:
            raise InvalidCredentialsError("Incorrect email or password")

        return AuthResponse(
            user=self._to_user_public(user),
            tokens=self._issue_token_pair(str(user.id)),
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenPair:
        """
        Exchanges a valid, unexpired refresh token for a brand-new
        access/refresh token pair.

        Business rules enforced here, in order:
        1. Token validity + type — decode_token() is called with
           expected_type=TokenType.REFRESH. This does three things at
           once (per core.security's own docstring): verifies the
           signature, checks the token hasn't expired, AND confirms the
           `type` claim is literally "refresh" — a valid, unexpired
           ACCESS token passed to this method is rejected here, because
           its type claim won't match. Any failure from decode_token()
           (a jose.JWTError) is caught and re-raised as
           InvalidTokenError, so this service never leaks raw
           jose/JWT-library exception types to its callers.
        2. User existence — the user id decoded from the token must
           still resolve to an actual user via the repository. This
           matters because a refresh token can be valid (correctly
           signed, not expired, right type) while pointing at a user
           that no longer exists — e.g. the account was deleted AFTER
           the token was issued but BEFORE it expired. That specific
           case raises UserNotFoundError, distinct from InvalidTokenError,
           since the token itself was legitimate; what's missing is the
           account it refers to.
        3. Inactive-account check — folded into the SAME UserNotFoundError
           as "doesn't exist": a deactivated account should not be able
           to mint fresh tokens via refresh, and from the caller's
           perspective there's no meaningful difference between "this
           user id doesn't exist" and "this user id exists but is
           deactivated" — both mean "you cannot get new tokens for this
           account."
        4. Token reissuance — on success, a COMPLETELY NEW token pair is
           generated (both access AND refresh, not just access). Issuing
           a new refresh token on every use, rather than reusing the
           same one until its own expiry, is a stronger security
           posture: an old refresh token becomes useless the moment a
           newer one has been issued from it, reducing how long a
           leaked-but-unused refresh token stays viable.

        Returns:
            A brand-new TokenPair (both access_token and refresh_token
            are freshly issued).

        Raises:
            InvalidTokenError: if the token is malformed, expired, has
                an invalid signature, or is not a refresh-type token.
            UserNotFoundError: if the token is otherwise valid but the
                user id it refers to no longer exists or is inactive.
        """
        try:
            user_id = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        except JWTError as exc:
            raise InvalidTokenError("Refresh token is invalid or expired") from exc

        user = await self._users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise UserNotFoundError("The account associated with this token no longer exists")

        return self._issue_token_pair(user_id)

    # ------------------------------------------------------------------
    # Private helpers — not part of the service's public contract, only
    # used internally to avoid repeating the same mapping/issuance logic
    # across signup/login/refresh_tokens.
    # ------------------------------------------------------------------

    @staticmethod
    def _to_user_public(user) -> UserPublic:
        """
        Maps a repository-returned user object to the API-facing
        UserPublic schema. Kept as a private static helper (rather than
        inlined into signup/login separately) so there's exactly ONE
        place that decides how a user document becomes a public
        response — and, not incidentally, exactly one place that could
        ever accidentally include password_hash, making it easy to audit.

        Note: no type hint on `user` here, and this file never imports
        app.models.User, per the "do not import or access app.models.User
        directly" requirement — this method relies on duck typing (it
        only needs .id, .email, .full_name, .created_at to exist on
        whatever UserRepository hands back).
        """
        return UserPublic(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            created_at=user.created_at,
        )

    @staticmethod
    def _issue_token_pair(user_id: str) -> TokenPair:
        """
        Issues a fresh access + refresh token pair for the given user id.
        The one place all three public methods above go through to
        create tokens, so "how tokens are issued" has a single
        implementation to change if it ever needs to.
        """
        return TokenPair(
            access_token=create_access_token(user_id),
            refresh_token=create_refresh_token(user_id),
        )