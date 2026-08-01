"""
PURPOSE
-------
API request/response contracts for CareerVault (Milestone 2). This file
contains ONLY Pydantic schemas — no database queries, no business rules
about what a user is allowed to do. Its one piece of real logic is
dispatching metadata validation to the correct per-item_type schema below,
which is a data-SHAPE concern (does this payload look right), not a
business-RULE concern (is this action allowed) — the latter belongs to
CareerVaultService, a later step in this milestone.
"""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.career_vault import VaultItemType

# ======================================================================
# Per-item_type metadata schemas
#
# Each uses ConfigDict(extra="forbid") so a field that doesn't belong to
# that item_type (e.g. "tech_stack" on a certificate) is REJECTED, not
# silently accepted and stored. This is what makes the vault's metadata
# field trustworthy despite being stored as a loose dict at the model
# layer — every value that reaches the database has already been shaped
# to match its declared item_type.
#
# ASSUMPTION FLAGGED: the architecture doc specifies concrete fields only
# for `certificate` (issuer, date) and `project` (tech_stack). The fields
# below for skill/achievement/education/experience are a reasonable
# minimal set, not specified in the frozen doc. They're isolated to this
# file — adjusting them later does not require touching the model,
# repository, or database.
# ======================================================================


class SkillMetadata(BaseModel):
    """Metadata shape for item_type == 'skill'."""

    model_config = ConfigDict(extra="forbid")

    proficiency_level: str | None = Field(
        default=None,
        description="e.g. 'beginner', 'intermediate', 'advanced', 'expert'",
        max_length=50,
    )
    years_of_experience: float | None = Field(default=None, ge=0, le=80)


class AchievementMetadata(BaseModel):
    """Metadata shape for item_type == 'achievement'."""

    model_config = ConfigDict(extra="forbid")

    issuer: str | None = Field(default=None, max_length=200)
    date_achieved: date | None = None


class CertificateMetadata(BaseModel):
    """
    Metadata shape for item_type == 'certificate'. Field names match the
    architecture doc's own example (Section 4.1: "issuer"/"date").
    """

    model_config = ConfigDict(extra="forbid")

    issuer: str = Field(min_length=1, max_length=200)
    issue_date: date
    credential_url: str | None = Field(default=None, max_length=500)


class ProjectMetadata(BaseModel):
    """
    Metadata shape for item_type == 'project'. Field name matches the
    architecture doc's own example (Section 4.1: "tech_stack").
    """

    model_config = ConfigDict(extra="forbid")

    tech_stack: list[str] = Field(default_factory=list, max_length=30)
    project_url: str | None = Field(default=None, max_length=500)
    repository_url: str | None = Field(default=None, max_length=500)


class EducationMetadata(BaseModel):
    """Metadata shape for item_type == 'education'."""

    model_config = ConfigDict(extra="forbid")

    institution: str = Field(min_length=1, max_length=200)
    degree: str = Field(min_length=1, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    start_date: date
    end_date: date | None = None


class ExperienceMetadata(BaseModel):
    """Metadata shape for item_type == 'experience'."""

    model_config = ConfigDict(extra="forbid")

    company: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    start_date: date
    end_date: date | None = None
    employment_type: str | None = Field(
        default=None,
        description="e.g. 'full_time', 'internship', 'part_time'",
        max_length=50,
    )


# Lookup used by the dispatch validator below — the single place that
# maps an item_type to its metadata schema. Adding a new item_type later
# means adding one entry here, nowhere else in this file.
_METADATA_SCHEMA_BY_TYPE: dict[VaultItemType, type[BaseModel]] = {
    VaultItemType.SKILL: SkillMetadata,
    VaultItemType.ACHIEVEMENT: AchievementMetadata,
    VaultItemType.CERTIFICATE: CertificateMetadata,
    VaultItemType.PROJECT: ProjectMetadata,
    VaultItemType.EDUCATION: EducationMetadata,
    VaultItemType.EXPERIENCE: ExperienceMetadata,
}


def _validate_metadata_for_type(item_type: VaultItemType, metadata: dict) -> dict:
    """
    Shared dispatch logic used by both the create and update request
    schemas below. Looks up the correct metadata schema for item_type,
    validates the raw dict against it, and returns the validated,
    normalized dict (e.g. a date string becomes a real `date`, and any
    field not declared on that schema raises a validation error instead
    of being silently kept).
    """
    schema_class = _METADATA_SCHEMA_BY_TYPE[item_type]
    validated = schema_class.model_validate(metadata)
    return validated.model_dump(mode="json")


# ======================================================================
# Request schemas
# ======================================================================


class CareerVaultItemCreateRequest(BaseModel):
    """
    Request body for POST /api/v1/career-vault — creating a new vault
    item. Used by the router (a later step), which passes its validated
    fields into CareerVaultService.create_item(...).
    """

    item_type: VaultItemType
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    metadata: dict = Field(default_factory=dict)
    attachment_url: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_metadata_shape(self) -> "CareerVaultItemCreateRequest":
        """
        Runs after individual-field validation. Dispatches `metadata` to
        the schema matching `item_type`, and replaces self.metadata with
        the validated, normalized result. A metadata payload that
        doesn't match its declared item_type (missing a required field,
        wrong type, or an unexpected extra field) fails HERE, as part of
        request validation — the router/service never sees a
        mismatched item_type/metadata pair.
        """
        self.metadata = _validate_metadata_for_type(self.item_type, self.metadata)
        return self

    @model_validator(mode="after")
    def strip_title(self) -> "CareerVaultItemCreateRequest":
        """Normalizes whitespace-only-looking titles the same way Milestone 1's full_name validator did."""
        stripped = self.title.strip()
        if not stripped:
            raise ValueError("Title cannot be blank")
        self.title = stripped
        return self


class CareerVaultItemUpdateRequest(BaseModel):
    """
    Request body for PATCH /api/v1/career-vault/{id} — partial update of
    an existing item. Used by the router, passed into
    CareerVaultService.update_item(...).

    DESIGN CHOICE: item_type is deliberately NOT editable here. A vault
    item's type is treated as fixed at creation — changing a 'project'
    into a 'certificate' after the fact would mean its metadata shape
    needs to change too, which is a delete-and-recreate operation
    conceptually, not an update. If item_type needs to change, the
    client creates a new item and deletes the old one; this schema does
    not support mutating it in place.

    All other fields are Optional — a client updating one field (e.g.
    just `description`) should not be forced to resend the entire item.
    Because item_type can't change, metadata validation here is against
    whatever item_type the EXISTING item already has — which means this
    schema alone cannot fully validate metadata (it doesn't know the
    existing item's type). That check is necessarily deferred to
    CareerVaultService (the next step), which loads the existing item
    first, then validates any provided metadata against ITS item_type
    before calling the repository.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    metadata: dict | None = None
    attachment_url: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def strip_title_if_provided(self) -> "CareerVaultItemUpdateRequest":
        if self.title is None:
            return self
        stripped = self.title.strip()
        if not stripped:
            raise ValueError("Title cannot be blank")
        self.title = stripped
        return self


# ======================================================================
# Response schema
# ======================================================================


class CareerVaultItemPublic(BaseModel):
    """
    Response shape returned by every CareerVault endpoint (create, get,
    list, update). Unlike UserPublic in Milestone 1, there's no sensitive
    field to exclude here (no password-equivalent on a vault item) — this
    schema mirrors the model's fields directly, but is still defined
    separately from CareerVaultItem (the model) to keep the API contract
    independent of the DB shape, consistent with the rest of this
    codebase's pattern.
    """

    id: str
    item_type: VaultItemType
    title: str
    description: str | None
    metadata: dict
    attachment_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)