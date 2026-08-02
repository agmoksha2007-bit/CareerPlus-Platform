"""
PURPOSE
-------
API request/response contracts for the Skills Engine (Milestone 3,
architecture doc Section 4.0). This file contains ONLY Pydantic schemas —
no database queries, no proficiency-scoring logic, no skill-name
normalization, no AI calls. Those all belong to
app/services/skills_engine_service.py (a later step).

Two distinct concerns live here, matching the two Documents in
app/models/skill.py:
  - Taxonomy schemas: request/response shapes for platform-curated
    skills_taxonomy entries.
  - Signal/profile schemas: the internal input shape used to report a
    skill-relevant event, and the response shape for a user's computed
    skill profile.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.skill import SkillCategory

# ======================================================================
# Taxonomy schemas
# ======================================================================


class SkillTaxonomyCreateRequest(BaseModel):
    """
    Request body for creating a new canonical taxonomy entry. Used by
    app/routers/skill.py (a later step), passed into
    SkillsEngineService.create_taxonomy_entry(...).
    """

    name: str = Field(min_length=1, max_length=100)
    category: SkillCategory
    aliases: list[str] = Field(default_factory=list, max_length=50)
    related_skill_ids: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        """Same non-blank-after-strip pattern used throughout this codebase
        (e.g. UserSignupRequest.full_name in Milestone 1)."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("Skill name cannot be blank")
        return stripped

    @field_validator("aliases")
    @classmethod
    def aliases_must_not_contain_blanks(cls, value: list[str]) -> list[str]:
        """Rejects a list containing an empty/whitespace-only alias —
        allowing one would defeat the purpose of aliases (matching real
        alternate spellings), and would silently pollute search results
        in SkillTaxonomyRepository.search()."""
        for alias in value:
            if not alias.strip():
                raise ValueError("Aliases cannot be blank")
        return value


class SkillTaxonomyUpdateRequest(BaseModel):
    """
    Request body for editing an existing taxonomy entry. All fields
    optional — a client correcting just one alias should not be forced
    to resend the entire entry, same partial-update pattern as
    CareerVaultItemUpdateRequest in Milestone 2.

    DESIGN CHOICE: category is intentionally NOT included as editable
    here. Changing a skill's category after other modules have already
    referenced/filtered by it is a data-migration-shaped concern, not an
    ordinary field edit — same reasoning CareerVaultItemUpdateRequest
    used to keep item_type immutable after creation.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    aliases: list[str] | None = Field(default=None, max_length=50)
    related_skill_ids: list[str] | None = Field(default=None, max_length=50)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank_if_provided(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("Skill name cannot be blank")
        return stripped

    @field_validator("aliases")
    @classmethod
    def aliases_must_not_contain_blanks_if_provided(
        cls, value: list[str] | None
    ) -> list[str] | None:
        if value is None:
            return value
        for alias in value:
            if not alias.strip():
                raise ValueError("Aliases cannot be blank")
        return value


class SkillTaxonomyPublic(BaseModel):
    """
    Response shape for a single taxonomy entry — returned by create,
    get, list, and update endpoints alike, same one-schema-per-resource
    pattern as CareerVaultItemPublic in Milestone 2.
    """

    id: str
    name: str
    category: SkillCategory
    aliases: list[str]
    related_skill_ids: list[str]

    model_config = ConfigDict(from_attributes=True)


# ======================================================================
# Signal / profile schemas
# ======================================================================


class SkillSignalInput(BaseModel):
    """
    Describes ONE raw, already-occurred event relevant to a user's skill
    profile (e.g. "this user added a CareerVault project mentioning
    this skill"). This is an INTERNAL contract — its primary caller is
    Python code (SkillsEngineService.record_signal, and in future
    milestones, other services that depend on it per architecture doc
    Section 3.3), not necessarily a public HTTP request body, since the
    Skills Engine's write path is described as internal in the
    architecture doc's API overview (Section 8).

    Deliberately contains NO proficiency_score or confidence field: per
    your instruction, this schema does not decide what a signal is
    WORTH — it only describes that the signal happened. Turning a
    sequence of these into a score is SkillsEngineService's job.
    """

    skill_id: str = Field(min_length=1)
    module: str = Field(min_length=1, max_length=100)
    reference_id: str = Field(min_length=1)
    signal_type: str = Field(min_length=1, max_length=100)


class UserSkillEntryPublic(BaseModel):
    """
    Response shape for one skill within a user's profile — always
    returned embedded inside UserSkillProfilePublic below, never
    standalone (matching UserSkillEntry being an embedded, non-Document
    model in app/models/skill.py).

    Includes `sources` deliberately: per architecture doc Section 4.0,
    per-skill traceability back to the contributing events is a stated
    product property, not an internal detail to withhold from the API
    consumer.
    """

    skill_id: str
    proficiency_score: float
    confidence: float
    sources: list["SkillSignalSourcePublic"]

    model_config = ConfigDict(from_attributes=True)


class SkillSignalSourcePublic(BaseModel):
    """
    Response shape for one entry in UserSkillEntryPublic.sources —
    mirrors app.models.skill.SkillSignalSource's fields exactly, kept as
    a separate response schema rather than reusing the model directly,
    consistent with every other model/schema split in this codebase.
    """

    module: str
    reference_id: str
    signal_type: str
    contributed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserSkillProfilePublic(BaseModel):
    """
    Response shape for a user's complete skill profile. Returned by
    SkillsEngineService.get_profile(...) and, in a later step, by the
    profile-read router endpoint.
    """

    user_id: str
    skills: list[UserSkillEntryPublic]
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)