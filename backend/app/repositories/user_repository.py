"""
PURPOSE
-------
Data access layer for the User aggregate. This is the ONLY file (besides
app/core/database.py, which just registers the model) that imports Beanie
querying against app.models.User directly.

AuthService (a later step) depends on THIS class, never on Beanie/User
directly — that indirection is what the Router -> Service -> Repository ->
Model layering (architecture doc Section 3.1) exists to buy: business logic
stays testable and swappable without knowing MongoDB exists.
"""
from beanie import PydanticObjectId

from app.models.user import User


class UserRepository:
    """
    No business rules live here — only data access. "Is this email
    already taken?" is a business rule (AuthService's job); "fetch the
    user document with this email" is data access (this class's job).
    Keeping that boundary strict is what keeps AuthService testable
    without a real database.
    """

    async def get_by_email(self, email: str) -> User | None:
        """
        Looks up a user by email. Lower-cases the input before querying
        so "Ada@Example.com" and "ada@example.com" resolve to the same
        stored record — storage-side normalization happens in create()
        below, and this method normalizes its OWN input the same way, so
        a caller doesn't have to remember to lower-case before calling.

        Returns None (not an exception) when no match is found — "no
        such user" is a completely normal, expected outcome for this
        method (e.g. during login, or during signup's duplicate-email
        check), not an error condition.
        """
        return await User.find_one(User.email == email.lower())

    async def get_by_id(self, user_id: str) -> User | None:
        """
        Looks up a user by their MongoDB ObjectId, passed in as a string
        (which is how it arrives everywhere it's used — decoded from a
        JWT's `sub` claim, or from a URL path parameter). The string ->
        PydanticObjectId conversion can raise if the string isn't a
        valid ObjectId shape at all (e.g. a garbage/tampered token
        subject) — that's caught here and treated the same as "not
        found," rather than letting an exception escape to the caller.
        This means callers (like the get_current_user dependency, a
        later step) only ever have to handle one case — "user is None"
        — instead of also needing to catch a malformed-id exception
        separately.
        """
        try:
            object_id = PydanticObjectId(user_id)
        except Exception:
            return None
        return await User.get(object_id)

    async def create(self, email: str, password_hash: str, full_name: str) -> User:
        """
        Creates and persists a new user. Takes password_hash, never a
        plaintext password — hashing happens in core.security, called by
        AuthService BEFORE this method is invoked. This repository never
        sees or handles a raw password, which is one more structural
        guarantee (alongside UserPublic excluding password_hash) that
        plaintext passwords can't leak into the wrong place by accident.

        Lower-cases the email at the point of storage — the single place
        that decides "this is how emails are normalized in the
        database," matched by get_by_email()'s own lower-casing of its
        lookup input above.
        """
        user = User(email=email.lower(), password_hash=password_hash, full_name=full_name)
        await user.insert()
        return user