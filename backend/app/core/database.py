"""
PURPOSE
-------
Owns the MongoDB connection lifecycle for the application: opening a single
Motor client at process startup and closing it at shutdown, and registering
every Beanie document model so the ODM knows what collections exist.

Called exactly once at startup, via main.py's lifespan handler (a later
step) — never per-request. Opening a new Motor client per request would
exhaust connections under any real load.

Only Milestone-1 models are registered here. Future-milestone models
(career_vault, skills, etc.) must not be added until their own milestone
is built, per the "no future-milestone code" rule.
"""
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.models.user import User
from app.models.career_vault import CareerVaultItem
from app.models.skill import SkillTaxonomyEntry, UserSkillProfile
from app.models.career_assessment import AssessmentAttempt

# Module-level reference to the Motor client so close_database_connection()
# can reach it. Starts as None; set inside connect_to_database(). Kept at
# module scope rather than returned/passed around, because the lifespan
# handler in main.py only needs to call connect/close — it doesn't need to
# hold a reference to the client itself.
_client: AsyncIOMotorClient | None = None


async def connect_to_database() -> None:
    """
    Opens the MongoDB connection and initializes Beanie.

    Called once, from main.py's lifespan startup phase. `init_beanie`
    registers each Document subclass listed in `document_models` — this
    is what turns `User.find_one(...)`, `user.insert()`, etc. into
    working calls against the `users` collection.
    """
    global _client
    _client = AsyncIOMotorClient(settings.MONGODB_URI)
    await init_beanie(
        database=_client[settings.MONGODB_DB_NAME],
        document_models=[
            User,
            CareerVaultItem,
            SkillTaxonomyEntry,
            UserSkillProfile,
            AssessmentAttempt
            # Future-milestone models are added here ONLY when their
            # milestone is built — e.g. CareerVaultItem in Milestone 2,
            # SkillTaxonomyEntry / UserSkillProfile in Milestone 3.
        ],
    )


async def close_database_connection() -> None:
    """
    Closes the MongoDB connection cleanly. Called once, from main.py's
    lifespan shutdown phase, so the process doesn't leave a dangling
    connection open when it exits.
    """
    if _client is not None:
        _client.close()