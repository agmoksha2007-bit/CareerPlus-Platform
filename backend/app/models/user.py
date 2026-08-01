"""
PURPOSE
-------
Beanie document schema for the `users` collection — the persistence layer
for Milestone 1 authentication (architecture doc Section 4.1, Group A).

This is the DB shape only. It is NOT the API contract — request/response
shapes for signup/login live in app/schemas/ (a later step), kept
deliberately separate so a field like password_hash can never leak into an
HTTP response just because someone forgot to exclude it; the response
schema simply never declares that field in the first place.
"""
from datetime import datetime, timezone

from beanie import Document, Indexed
from pydantic import Field


class User(Document):
    # --------------------------------------------------------------
    # email: the user's login identifier.
    #
    # - Indexed(str, unique=True) does two things at once: it's a plain
    #   `str` type annotation for Pydantic validation, AND it tells Beanie
    #   to create a unique index on this field in MongoDB. The unique
    #   index is the actual enforcement mechanism against duplicate
    #   accounts — the application-level "does this email already exist"
    #   check in AuthService is a UX nicety (a clean 409 error instead of
    #   a raw DB exception), not the source of truth for uniqueness.
    # - Storage convention: always lower-cased before being written here
    #   (enforced in the repository layer, not this model) so
    #   "Ada@Example.com" and "ada@example.com" are treated as the same
    #   account. This model doesn't lower-case it itself, because a
    #   Beanie Document should describe the DB shape, not perform
    #   normalization logic — that's the repository's job.
    # --------------------------------------------------------------
    email: Indexed(str, unique=True)  # type: ignore[valid-type]

    # --------------------------------------------------------------
    # password_hash: bcrypt hash, never the plaintext password.
    #
    # Named `password_hash`, not `password`, deliberately — the name
    # itself is a guardrail. If someone accidentally wired this field
    # into an API response schema, "password_hash" reads as obviously
    # wrong in a way "password" might not.
    # --------------------------------------------------------------
    password_hash: str

    # --------------------------------------------------------------
    # full_name: display name, required at signup.
    #
    # No email-style validation needed here (that belongs to the signup
    # request schema, not the DB model) — but note there's intentionally
    # NO uniqueness constraint on full_name. Multiple users can share a
    # name; only email identifies an account.
    # --------------------------------------------------------------
    full_name: str

    # --------------------------------------------------------------
    # is_active: soft-disable flag.
    #
    # Exists so an account can be deactivated (e.g. by an admin, or by
    # the user closing their account) WITHOUT deleting their data or
    # breaking foreign-key-style references from other collections in
    # later milestones (career_vault_items.user_id, etc., per the
    # architecture doc). AuthService's login() and the get_current_user
    # dependency both check this flag — a deactivated account can't log
    # in or use an existing token, even if the token hasn't expired yet.
    # --------------------------------------------------------------
    is_active: bool = True

    # --------------------------------------------------------------
    # created_at / updated_at: audit timestamps.
    #
    # default_factory (not a fixed default value) means each new User
    # gets its OWN current timestamp at creation time, evaluated when the
    # document is instantiated — not once at class-definition time, which
    # is a classic Python mutable-default-style bug this avoids.
    #
    # timezone.utc is explicit and non-negotiable: storing naive
    # datetimes is a recurring source of subtle bugs once the app has
    # users/servers in different timezones. Everything is UTC in the
    # database; any timezone conversion for display happens in the
    # frontend.
    #
    # NOTE: updated_at is declared here but this Milestone does not yet
    # implement any "edit user" endpoint that would mutate it — it's
    # included now because retrofitting an audit timestamp onto an
    # existing collection later is more disruptive than including it
    # from the start. It will start being actively updated once a
    # profile-edit endpoint exists in a future milestone.
    # --------------------------------------------------------------
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        # Explicit collection name. Beanie would otherwise default to a
        # lowercased class name ("user"), which happens to be similar
        # here but shouldn't be relied on implicitly — being explicit
        # means the collection name survives a future class rename
        # unchanged, and matches the "users" collection name used
        # throughout the architecture doc (Section 4.1).
        name = "users"