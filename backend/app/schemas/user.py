"""
PURPOSE
-------
User-related API request/response schemas (Pydantic v2). These are the
contracts routers use — distinct from app.models.User, which is the
database shape. Token-related schemas (TokenPair, AuthResponse, etc.)
belong in app/schemas/auth.py, not here.
"""
import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

# Minimum password length, defined once and referenced below rather than
# hardcoded inline — if this needs to change later, it changes in one place.
_PASSWORD_MIN_LENGTH = 8
_PASSWORD_MAX_LENGTH = 128


class UserSignupRequest(BaseModel):
    """
    Request body for POST /api/v1/auth/signup.

    Validation here runs BEFORE any service/business logic is reached —
    a malformed request never gets as far as AuthService.signup(). This
    is FastAPI/Pydantic's automatic request validation, distinct from
    business-rule validation (like "is this email already taken?"),
    which belongs in the service layer because it requires a database
    lookup, not just inspecting the request body in isolation.
    """

    # EmailStr (from pydantic's email-validator extra) enforces valid
    # email FORMAT at the schema level — "not-an-email" is rejected
    # before the request even reaches a router function. It does NOT
    # check whether the email is already registered; that's a business
    # rule, checked later in AuthService against the database.
    email: EmailStr

    # Field(min_length=..., max_length=...) enforces length bounds.
    # max_length=128 matters as much as min_length=8: without an upper
    # bound, a client could submit a multi-megabyte string as a
    # "password," which bcrypt would then have to hash — an easy,
    # free denial-of-service vector if left unbounded.
    password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=_PASSWORD_MAX_LENGTH)

    # full_name: bounded length (1-120). min_length=1 alone isn't quite
    # enough to reject "   " (whitespace-only) — that's why there's a
    # dedicated field_validator below that strips and re-checks.
    full_name: str = Field(min_length=1, max_length=120)

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, value: str) -> str:
        """
        Enforces password complexity beyond mere length: at least one
        uppercase letter, one lowercase letter, and one digit. This runs
        as part of Pydantic's validation phase, so a weak password is
        rejected with a 422 (via the validation error handler built in
        the exceptions.py step) before AuthService or the database are
        ever touched.
        """
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", value):
            raise ValueError("Password must contain at least one digit")
        return value

    @field_validator("full_name")
    @classmethod
    def full_name_must_not_be_blank(cls, value: str) -> str:
        """
        Rejects a name that's technically non-empty but meaningless
        (e.g. "   "). Returns the STRIPPED value, not just validates it —
        so "  Ada Lovelace  " is normalized to "Ada Lovelace" before it
        ever reaches AuthService, rather than every downstream consumer
        needing to remember to strip it themselves.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("Full name cannot be blank")
        return stripped


class UserUpdateRequest(BaseModel):
    """
    Request body for a future profile-update endpoint. Not wired to any
    router in Milestone 1 (no PATCH /users/me endpoint exists yet — that
    would be inventing scope beyond what this milestone's routers cover),
    but the schema is defined now since it belongs in this file
    (user-related request contracts) rather than being retrofitted later.

    All fields are Optional: a client updating their profile should be
    able to send only the field(s) they're changing, not be forced to
    resend their entire profile on every request.
    """
    full_name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("full_name")
    @classmethod
    def full_name_must_not_be_blank_if_provided(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("Full name cannot be blank")
        return stripped


class UserPublic(BaseModel):
    """
    Response shape for any endpoint returning user data — signup, login,
    and GET /users/me all return this. Deliberately excludes
    password_hash, is_active, and updated_at:

    - password_hash: must never leave the server, under any
      circumstance. Excluding it here, rather than remembering to strip
      it at every call site, is what makes that a structural guarantee
      instead of a habit someone can forget.
    - is_active / updated_at: internal bookkeeping fields with no
      current use on the client side. Left out to keep the public
      contract minimal — fields are added to this schema when a real
      consumer needs them, not speculatively.

    model_config = {"from_attributes": True} allows this schema to be
    constructed directly from a Beanie `User` document's attributes
    (user.email, user.full_name, ...) via UserPublic.model_validate(user),
    not just from a plain dict — convenient when mapping a DB object to
    an API response in routers.
    """
    id: str
    email: EmailStr
    full_name: str
    created_at: datetime

    model_config = {"from_attributes": True}