"""
PURPOSE
-------
Beanie document schema for the `career_vault_items` collection —
Milestone 2's foundational data store (architecture doc Section 4.1,
Group A: Foundation & Self-Knowledge).

This is the persistence layer only. API-facing request/response shapes,
including per-item_type validation of the `metadata` field, belong in
app/schemas/career_vault.py (a later step in this milestone) — not here,
per the architecture doc's explicit instruction that metadata shape
validation happens "at the Pydantic schema layer per item_type."
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field


class VaultItemType(str, Enum):
    """
    The fixed set of item types a CareerVault entry can be, per
    architecture doc Section 4.1. A str Enum (not a free-text field)
    means an invalid type value is rejected at validation time, not
    discovered later as a data-quality problem.
    """
    SKILL = "skill"
    ACHIEVEMENT = "achievement"
    CERTIFICATE = "certificate"
    PROJECT = "project"
    EDUCATION = "education"
    EXPERIENCE = "experience"


class CareerVaultItem(Document):
    # user_id: indexed (per architecture doc Section 4.5's near-universal
    # "user_id indexed on every user-scoped collection" rule), but NOT
    # unique — one user has many vault items, unlike User.email which
    # identifies exactly one account.
    user_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]

    item_type: VaultItemType

    title: str = Field(min_length=1, max_length=200)

    # Optional: a skill entry might just be a title ("Python"), while a
    # project or certificate typically wants a fuller description.
    description: str | None = Field(default=None, max_length=2000)

    # Intentionally loose (dict[str, Any]) at the MODEL layer — its
    # actual shape varies by item_type (e.g. {"issuer", "date"} for a
    # certificate, {"tech_stack"} for a project). Per the architecture
    # doc, that shape is validated at the schema layer, not here.
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Reference to an uploaded file (e.g. a certificate scan), stored in
    # object storage — this field is only ever a URL, never file bytes.
    # No object-storage integration exists yet in this codebase; this
    # field is simply ready to hold that URL once one does.
    attachment_url: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        # Explicit collection name, matching architecture doc Section 4.1
        # exactly — not left to Beanie's default lowercased-classname
        # behavior.
        name = "career_vault_items"