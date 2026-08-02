"""
PURPOSE
-------
Beanie document schemas for the Skills Engine — the cross-cutting
component defined in architecture doc Section 4.0. Two top-level
collections live in this one file, per the doc's own folder-structure
comment:

  - SkillTaxonomyEntry  -> "skills_taxonomy"    (platform-curated, canonical)
  - UserSkillProfile    -> "user_skill_profiles" (per-user, one per user)

SkillSignalSource and UserSkillEntry are NOT Beanie Documents — they are
plain Pydantic models embedded inside UserSkillProfile.skills, always
read/written as part of their parent profile (never queried on their
own), matching Section 4.0's description of `skills` and `sources` as
embedded arrays.

This file contains NO business logic: how a proficiency_score is computed
from signals, and how free-text skill mentions get normalized against the
taxonomy, are service-layer concerns (app/services/skills_engine_service.py,
a later step) — not this model's job.
"""
from datetime import datetime, timezone
from enum import Enum

from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field


class SkillCategory(str, Enum):
    """
    The fixed set of skill categories named in architecture doc Section
    4.0. A str Enum, not free text, so an invalid category is rejected
    at validation time rather than discovered later as a data-quality
    problem — same reasoning as VaultItemType in Milestone 2.
    """
    PROGRAMMING_LANGUAGE = "programming_language"
    FRAMEWORK = "framework"
    SOFT_SKILL = "soft_skill"
    DOMAIN_KNOWLEDGE = "domain_knowledge"


class SkillTaxonomyEntry(Document):
    """
    A single canonical skill in the platform-wide taxonomy. Per the
    architecture doc: "every module that references a skill... points at
    an entry here rather than storing free-text skill names, which is
    what makes cross-module skill matching possible at all."

    This collection is platform-curated content (admin-maintained),
    not user-generated — no user_id field, unlike every other
    Milestone-2-onward collection.
    """

    # Unique: two taxonomy entries cannot share a canonical name. This
    # is the field other modules will match against when normalizing
    # free-text skill mentions.
    name: Indexed(str, unique=True)  # type: ignore[valid-type]

    category: SkillCategory

    # Alternate names/spellings that should resolve to THIS entry (e.g.
    # "JS" and "Javascript" both aliasing to the canonical "JavaScript").
    # Used by the AI-assisted skill_extraction touchpoint (architecture
    # doc Section 7.1) in a later milestone — not implemented here, only
    # the field it will need is defined now.
    aliases: list[str] = Field(default_factory=list)

    # Supports "you have X, here's a related skill to build next" in
    # Career Guidance/Roadmaps (future milestones). References OTHER
    # SkillTaxonomyEntry documents by id — not embedded, since a
    # relationship between two taxonomy entries doesn't belong to either
    # one exclusively.
    related_skill_ids: list[PydanticObjectId] = Field(default_factory=list)

    class Settings:
        # Explicit collection name, matching architecture doc Section
        # 4.0 exactly.
        name = "skills_taxonomy"


class SkillSignalSource(BaseModel):
    """
    Embedded record of ONE event that contributed to a skill's
    proficiency_score. Per architecture doc Section 4.0: "every
    proficiency number is traceable back to the events that produced it,
    not an opaque black box." This is what makes that traceability
    concrete — every entry in UserSkillEntry.sources is one of these.

    NOT a Beanie Document: always read/written as part of its parent
    UserSkillProfile, never queried independently.
    """

    # Which module produced this signal (e.g. "career_vault",
    # "aptitude_practice" in a later milestone). A plain string, not an
    # enum, because the full set of contributing modules will only be
    # known once every milestone that can produce a skill signal is
    # built — enumerating them now would mean editing this model every
    # time a new module ships, which the architecture doc's own
    # incremental-milestone approach argues against.
    module: str

    # The id of whatever record produced this signal (e.g. a
    # CareerVaultItem's id). Deliberately a plain string, not
    # PydanticObjectId: a signal can originate from ANY collection, each
    # with its own id space, and this model has no need (and per your
    # rules, no basis) to assume which future collections exist.
    reference_id: str

    # What KIND of event this was (e.g. "vault_item_added",
    # "problem_passed" in later milestones). Same reasoning as `module`
    # for staying a plain string rather than a not-yet-fully-known enum.
    signal_type: str

    contributed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserSkillEntry(BaseModel):
    """
    Embedded record of a user's proficiency in ONE skill, plus every
    signal that contributed to that score. One UserSkillProfile document
    holds a list of these — one per distinct skill the user has any
    signal for.

    NOT a Beanie Document — always accessed as part of its parent
    UserSkillProfile.
    """

    skill_id: PydanticObjectId  # references SkillTaxonomyEntry._id

    # HOW this number is computed from `sources` is a service-layer
    # concern (SkillsEngineService, a later step) — this model only
    # stores the result.
    proficiency_score: float = Field(ge=0, le=100)

    # Separate from proficiency_score: reflects how MUCH signal exists
    # (e.g. one passed programming problem vs. twenty), not how skilled
    # the user is. A high score from a single signal should be treated
    # differently downstream (e.g. by Career Guidance) than the same
    # score backed by dozens of signals — that comparison is only
    # possible if confidence is tracked separately from the score itself.
    confidence: float = Field(ge=0, le=1)

    sources: list[SkillSignalSource] = Field(default_factory=list)


class UserSkillProfile(Document):
    """
    A single user's complete skill profile — one document per user,
    enforced by the unique index below, per architecture doc Section
    4.0: "one profile per user."
    """

    user_id: Indexed(PydanticObjectId, unique=True)  # type: ignore[valid-type]

    skills: list[UserSkillEntry] = Field(default_factory=list)

    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "user_skill_profiles"