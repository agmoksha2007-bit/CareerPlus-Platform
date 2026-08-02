"""
PURPOSE
-------
Business logic for the Skills Engine (Milestone 3): taxonomy management
and per-user skill signal recording/profile computation. This layer
depends ONLY on SkillTaxonomyRepository and UserSkillProfileRepository —
it never imports Beanie or app.models.skill directly, and it never
constructs a MongoDB query itself.

This is the SINGLE place proficiency-scoring logic exists, per
architecture doc Section 4.0 ("Proficiency scoring logic... lives inside
this service") — every future caller (career_vault_service,
roadmap_service, etc., per Section 3.3) gets identical scoring behavior
by going through record_signal() here, rather than each computing its own
approximation.
"""
from datetime import datetime, timezone

from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import SkillNameAlreadyExistsError, SkillTaxonomyEntryNotFoundError
from app.models.skill import SkillCategory, SkillSignalSource, UserSkillEntry
from app.repositories.skill_repository import SkillTaxonomyRepository, UserSkillProfileRepository
from app.schemas.skill import (
    SkillSignalSourcePublic,
    SkillTaxonomyPublic,
    UserSkillEntryPublic,
    UserSkillProfilePublic,
)

# ----------------------------------------------------------------------
# Scoring constants — deliberately simple (see explanation above this
# code block). Not tuned against real data; a placeholder rule, isolated
# here so it can be refined later without touching anything that CALLS
# record_signal().
# ----------------------------------------------------------------------
_SCORE_INCREMENT_PER_SIGNAL = 10.0
_MAX_PROFICIENCY_SCORE = 100.0
_SIGNALS_FOR_FULL_CONFIDENCE = 5


class SkillsEngineService:
    """
    Orchestrates SkillTaxonomyRepository and UserSkillProfileRepository.
    Holds no state beyond the two repositories it's constructed with —
    same cheap-per-request pattern as every prior service.
    """

    def __init__(
        self,
        taxonomy_repository: SkillTaxonomyRepository,
        profile_repository: UserSkillProfileRepository,
    ):
        self._taxonomy_repo = taxonomy_repository
        self._profile_repo = profile_repository

    # ------------------------------------------------------------------
    # Taxonomy management
    # ------------------------------------------------------------------

    async def create_taxonomy_entry(
        self,
        name: str,
        category: SkillCategory,
        aliases: list[str],
        related_skill_ids: list[str],
    ) -> SkillTaxonomyPublic:
        """
        Creates a new canonical taxonomy entry.

        No pre-check for an existing name is performed here — the
        unique index on SkillTaxonomyEntry.name (Step 1) is the real
        enforcement. This method's job is to translate the resulting
        DuplicateKeyError into a clean, structured
        SkillNameAlreadyExistsError, same relationship as
        AuthService.signup() has to User.email's unique index.

        Raises:
            SkillNameAlreadyExistsError: if a taxonomy entry with this
                name already exists.
        """
        try:
            entry = await self._taxonomy_repo.create(
                name=name,
                category=category,
                aliases=aliases,
                related_skill_ids=[PydanticObjectId(rid) for rid in related_skill_ids],
            )
        except DuplicateKeyError as exc:
            raise SkillNameAlreadyExistsError(
                f"A skill named '{name}' already exists in the taxonomy"
            ) from exc

        return self._to_taxonomy_public(entry)

    async def update_taxonomy_entry(self, entry_id: str, updates: dict) -> SkillTaxonomyPublic:
        """
        Applies a partial update to an existing taxonomy entry.

        `updates` is expected to be built by the router (a later step)
        via SkillTaxonomyUpdateRequest.model_dump(exclude_unset=True) —
        same convention as CareerVaultService.update_item in Milestone
        2. If `related_skill_ids` is present, its string ids are
        converted to PydanticObjectId here, before reaching the
        repository, since the repository layer only knows how to store
        what it's given, not how to interpret a request-shaped string id.

        Raises:
            SkillTaxonomyEntryNotFoundError: if no entry exists for this id.
        """
        if "related_skill_ids" in updates and updates["related_skill_ids"] is not None:
            updates["related_skill_ids"] = [
                PydanticObjectId(rid) for rid in updates["related_skill_ids"]
            ]

        entry = await self._taxonomy_repo.update(entry_id, updates)
        if entry is None:
            raise SkillTaxonomyEntryNotFoundError("Skill taxonomy entry not found")

        return self._to_taxonomy_public(entry)

    async def get_taxonomy_entry(self, entry_id: str) -> SkillTaxonomyPublic:
        """
        Retrieves a single taxonomy entry by id.

        Raises:
            SkillTaxonomyEntryNotFoundError: if no entry exists for this
                id (whether malformed or genuinely missing — same
                indistinguishable-at-this-layer pattern used throughout
                this codebase).
        """
        entry = await self._taxonomy_repo.get_by_id(entry_id)
        if entry is None:
            raise SkillTaxonomyEntryNotFoundError("Skill taxonomy entry not found")
        return self._to_taxonomy_public(entry)

    async def search_taxonomy(self, query: str, limit: int = 20) -> list[SkillTaxonomyPublic]:
        """
        Searches the taxonomy by name/alias substring. An empty result
        is a normal outcome (no matches), never an error — same
        philosophy as CareerVaultService.list_items.
        """
        entries = await self._taxonomy_repo.search(query, limit)
        return [self._to_taxonomy_public(entry) for entry in entries]

    async def list_taxonomy_by_category(
        self, category: SkillCategory, skip: int = 0, limit: int = 100
    ) -> list[SkillTaxonomyPublic]:
        """Lists taxonomy entries in one category, with pagination."""
        entries = await self._taxonomy_repo.list_by_category(category, skip, limit)
        return [self._to_taxonomy_public(entry) for entry in entries]

    # ------------------------------------------------------------------
    # Signal recording / profile retrieval
    # ------------------------------------------------------------------

    async def record_signal(
        self,
        user_id: PydanticObjectId,
        skill_id: str,
        module: str,
        reference_id: str,
        signal_type: str,
    ) -> UserSkillProfilePublic:
        """
        Records one skill-relevant event for a user and recomputes that
        skill's proficiency_score/confidence from its complete signal
        history. This is the ONLY way UserSkillEntry.proficiency_score
        is ever set — no other code path writes it.

        Steps, in order:
        1. Validates skill_id refers to a REAL taxonomy entry. A signal
           for a nonexistent skill is rejected outright — this is what
           keeps every UserSkillEntry.skill_id trustworthy as a
           reference, matching the traceability guarantee described in
           architecture doc Section 4.0.
        2. Loads the user's profile, creating an empty one via
           UserSkillProfileRepository.create() if this is the user's
           first signal ever — this get-or-create decision belongs
           here, not in the repository (per Step 3's design notes).
        3. Finds the existing UserSkillEntry for this skill within the
           profile, if any, and appends the new SkillSignalSource to its
           `sources` list — or creates a new entry with just this one
           source if the user has no prior signal for this skill.
        4. Recomputes proficiency_score/confidence from the resulting
           complete sources list (see _score_from_sources below) and
           persists the profile's full, updated skills list via
           UserSkillProfileRepository.update().

        Raises:
            SkillTaxonomyEntryNotFoundError: if skill_id does not refer
                to an existing taxonomy entry.
        """
        taxonomy_entry = await self._taxonomy_repo.get_by_id(skill_id)
        if taxonomy_entry is None:
            raise SkillTaxonomyEntryNotFoundError(
                "Cannot record a signal for a skill that is not in the taxonomy"
            )

        profile = await self._profile_repo.get_by_user_id(user_id)
        if profile is None:
            profile = await self._profile_repo.create(user_id)

        new_source = SkillSignalSource(
            module=module,
            reference_id=reference_id,
            signal_type=signal_type,
        )

        existing_entry_index = next(
            (
                index
                for index, entry in enumerate(profile.skills)
                if entry.skill_id == taxonomy_entry.id
            ),
            None,
        )

        if existing_entry_index is None:
            updated_sources = [new_source]
        else:
            updated_sources = profile.skills[existing_entry_index].sources + [new_source]

        recomputed_entry = self._recompute_entry(taxonomy_entry.id, updated_sources)

        new_skills = list(profile.skills)
        if existing_entry_index is None:
            new_skills.append(recomputed_entry)
        else:
            new_skills[existing_entry_index] = recomputed_entry

        updated_profile = await self._profile_repo.update(user_id, new_skills)
        return self._to_profile_public(updated_profile)

    async def get_profile(self, user_id: PydanticObjectId) -> UserSkillProfilePublic:
        """
        Retrieves a user's complete skill profile.

        A user who has never triggered a skill signal has no persisted
        profile document at all (per UserSkillProfileRepository.get_by_user_id's
        own documented behavior) — this is a normal state, not an error.
        In that case, this method returns a SYNTHESIZED empty profile
        (skills=[]) rather than raising, so callers (a future router
        endpoint, or another service reading a user's skills) never need
        a special "no profile yet" branch — an empty skills list already
        communicates that correctly. Nothing is written to the database
        by this read-only method.
        """
        profile = await self._profile_repo.get_by_user_id(user_id)
        if profile is None:
            return UserSkillProfilePublic(
                user_id=str(user_id),
                skills=[],
                updated_at=datetime.now(timezone.utc),
            )
        return self._to_profile_public(profile)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _recompute_entry(
        skill_id: PydanticObjectId, sources: list[SkillSignalSource]
    ) -> UserSkillEntry:
        """
        Computes proficiency_score and confidence from a skill's
        complete signal history. DELIBERATELY SIMPLE, per Step 5's
        instruction not to invent a detailed algorithm: each signal adds
        a fixed increment to the score (capped at 100), and confidence
        approaches 1.0 as signals accumulate (capped at 5 signals for
        full confidence). This is a placeholder rule, isolated to this
        one method — refining it later does not require touching
        record_signal()'s orchestration logic above.
        """
        score = min(_MAX_PROFICIENCY_SCORE, len(sources) * _SCORE_INCREMENT_PER_SIGNAL)
        confidence = min(1.0, len(sources) / _SIGNALS_FOR_FULL_CONFIDENCE)

        return UserSkillEntry(
            skill_id=skill_id,
            proficiency_score=score,
            confidence=confidence,
            sources=sources,
        )

    @staticmethod
    def _to_taxonomy_public(entry) -> SkillTaxonomyPublic:
        """The one place a SkillTaxonomyEntry becomes an API-facing SkillTaxonomyPublic."""
        return SkillTaxonomyPublic(
            id=str(entry.id),
            name=entry.name,
            category=entry.category,
            aliases=entry.aliases,
            related_skill_ids=[str(rid) for rid in entry.related_skill_ids],
        )

    @staticmethod
    def _to_profile_public(profile) -> UserSkillProfilePublic:
        """The one place a UserSkillProfile becomes an API-facing UserSkillProfilePublic."""
        return UserSkillProfilePublic(
            user_id=str(profile.user_id),
            skills=[
                UserSkillEntryPublic(
                    skill_id=str(entry.skill_id),
                    proficiency_score=entry.proficiency_score,
                    confidence=entry.confidence,
                    sources=[
                        SkillSignalSourcePublic(
                            module=source.module,
                            reference_id=source.reference_id,
                            signal_type=source.signal_type,
                            contributed_at=source.contributed_at,
                        )
                        for source in entry.sources
                    ],
                )
                for entry in profile.skills
            ],
            updated_at=profile.updated_at,
        )