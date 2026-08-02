"""
PURPOSE
-------
Data access layer for the Skills Engine (Milestone 3, architecture doc
Section 4.0). This is the ONLY file (besides app/core/database.py, which
just registers the models) that queries app.models.skill.SkillTaxonomyEntry
or app.models.skill.UserSkillProfile directly.

Contains NO business logic: no proficiency scoring, no skill-name
normalization, no recommendation logic, no AI calls. Every method here
either reads exactly what's stored or writes exactly what it's given —
"how a score is computed" and "which skill a free-text mention matches"
are SkillsEngineService concerns (a later step), never this file's.
"""
from beanie import PydanticObjectId
from beanie.operators import Or, RegEx

from app.models.skill import SkillCategory, SkillTaxonomyEntry, UserSkillEntry, UserSkillProfile


class SkillTaxonomyRepository:
    """
    Data access for the platform-curated skills_taxonomy collection.
    Unlike every other repository in this codebase so far, these methods
    are NOT user-scoped — taxonomy entries belong to the platform, not
    to any individual user, per architecture doc Section 4.0.
    """

    async def create(
        self,
        name: str,
        category: SkillCategory,
        aliases: list[str] | None = None,
        related_skill_ids: list[PydanticObjectId] | None = None,
    ) -> SkillTaxonomyEntry:
        """
        Creates and persists a new canonical taxonomy entry. Uniqueness
        of `name` is enforced by the unique index declared on the model
        (Step 1) — this method does not pre-check for an existing entry
        itself; a duplicate name will fail at the database level, and
        translating that into a clean domain exception is a
        service-layer concern (a later step), same pattern as
        AuthService.signup() relying on User.email's unique index as the
        real enforcement mechanism.
        """
        entry = SkillTaxonomyEntry(
            name=name,
            category=category,
            aliases=aliases or [],
            related_skill_ids=related_skill_ids or [],
        )
        await entry.insert()
        return entry

    async def get_by_id(self, entry_id: str) -> SkillTaxonomyEntry | None:
        """
        Fetches a single taxonomy entry by id. Returns None for both a
        malformed id and a genuinely missing entry — same
        "indistinguishable at this layer" pattern as
        CareerVaultRepository.get_by_id in Milestone 2, so callers only
        ever need to handle one case (None), never a separate
        malformed-id exception.
        """
        try:
            object_id = PydanticObjectId(entry_id)
        except Exception:
            return None
        return await SkillTaxonomyEntry.get(object_id)

    async def get_by_name(self, name: str) -> SkillTaxonomyEntry | None:
        """
        Fetches a taxonomy entry by its exact canonical name (not an
        alias — alias-aware lookup belongs to search() below, or to a
        future service-layer normalization step that checks both the
        canonical name AND aliases before deciding "no match"). Exact
        match, no case-folding: unlike User.email, skill names have
        meaningful casing (e.g. "JavaScript") that should not be
        silently normalized away at the storage layer.
        """
        return await SkillTaxonomyEntry.find_one(SkillTaxonomyEntry.name == name)

    async def search(self, query: str, limit: int = 20) -> list[SkillTaxonomyEntry]:
        """
        Case-insensitive substring search across BOTH the canonical name
        and the aliases list. This is what lets a future
        skill-normalization step (or a UI autocomplete, in a later
        milestone) find "Django" whether the input is "djang", "Djngo",
        or an alias like "django framework" — but this method only
        performs the search; deciding what a caller does with multiple
        matches (best match? all of them?) is not this method's concern.

        Uses beanie.operators.RegEx / Or rather than a raw MongoDB
        query dict, consistent with the production-ready Beanie usage
        established in prior milestones (typed field references, e.g.
        SkillTaxonomyEntry.name, rather than string field names).
        """
        return await SkillTaxonomyEntry.find(
            Or(
                RegEx(SkillTaxonomyEntry.name, query, options="i"),
                RegEx(SkillTaxonomyEntry.aliases, query, options="i"),
            )
        ).limit(limit).to_list()

    async def list_by_category(
        self, category: SkillCategory, skip: int = 0, limit: int = 100
    ) -> list[SkillTaxonomyEntry]:
        """
        Lists taxonomy entries belonging to one category, with basic
        pagination (skip/limit) since a category like
        "programming_language" could plausibly contain hundreds of
        entries as the taxonomy grows. Sorted by name for stable,
        predictable ordering across calls.
        """
        return (
            await SkillTaxonomyEntry.find(SkillTaxonomyEntry.category == category)
            .sort(+SkillTaxonomyEntry.name)
            .skip(skip)
            .limit(limit)
            .to_list()
        )
    async def update(self, entry_id: str, updates: dict) -> SkillTaxonomyEntry | None:
        """
        Applies a partial update to an existing taxonomy entry. `updates`
        is a dict of {field_name: new_value} — identical partial-update
        pattern to CareerVaultRepository.update (Milestone 2) and
        UserSkillProfileRepository.update (above). Returns the updated
        entry, or None if no entry exists for this id.
        """
        entry = await self.get_by_id(entry_id)
        if entry is None:
            return None
        for field_name, value in updates.items():
            setattr(entry, field_name, value)
        await entry.save()
        return entry


class UserSkillProfileRepository:
    """
    Data access for the per-user user_skill_profiles collection. Every
    method here IS user-scoped, per architecture doc Section 4.0: "one
    profile per user."
    """

    async def create(self, user_id: PydanticObjectId) -> UserSkillProfile:
        """
        Creates a new, empty skill profile for a user (skills=[]).
        Uniqueness of user_id is enforced by the unique index on the
        model (Step 1) — same reasoning as SkillTaxonomyRepository.create
        relying on the DB-level unique index rather than a
        check-then-create pattern here.
        """
        profile = UserSkillProfile(user_id=user_id)
        await profile.insert()
        return profile

    async def get_by_user_id(self, user_id: PydanticObjectId) -> UserSkillProfile | None:
        """
        Fetches a user's skill profile. Returns None if the user has no
        profile yet — a completely normal state (e.g. a brand-new user
        who hasn't triggered any skill signal yet), not an error
        condition. Deciding whether to lazily create one on first access
        is a service-layer decision (a later step), not this method's.
        """
        return await UserSkillProfile.find_one(UserSkillProfile.user_id == user_id)

    async def update(
        self, user_id: PydanticObjectId, skills: list[UserSkillEntry]
    ) -> UserSkillProfile | None:
        """
        Replaces a user's entire `skills` list with the one provided,
        and bumps `updated_at`. Takes the COMPLETE, already-computed
        list — this method does not merge, score, or deduplicate
        anything itself. By the time this is called, SkillsEngineService
        (a later step) has already done that work; this method's only
        job is persisting the result.

        Returns None if no profile exists yet for this user_id — the
        caller (service layer) decides whether that should trigger
        creating one via create() instead, or be treated as an error.
        """
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            return None

        from datetime import datetime, timezone

        profile.skills = skills
        profile.updated_at = datetime.now(timezone.utc)
        await profile.save()
        return profile

    async def delete(self, user_id: PydanticObjectId) -> bool:
        """
        Deletes a user's entire skill profile. Returns True if a profile
        was found and deleted, False if none existed — same
        found/not-found boolean pattern as
        CareerVaultRepository.delete in Milestone 2.
        """
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            return False
        await profile.delete()
        return True