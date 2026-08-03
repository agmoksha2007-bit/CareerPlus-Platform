"""
PURPOSE
-------
Beanie document schema for the `career_assessments` collection —
Milestone 4's foundational data store (architecture doc Section 4.1,
Group A: Foundation & Self-Knowledge).

This is the persistence layer only. How a raw AssessmentResponseItem
becomes an AssessmentResult (trait scores, recommended domains) is an
AI-interpretation concern (architecture doc Section 7.1's
assessment_interpretation touchpoint) — a future step in this milestone,
not this file's job. This model only defines the shape both states
(in-progress and interpreted) are stored in.

Class naming follows the architecture doc's own folder-structure comment
(Section 3.2): AssessmentAttempt, AssessmentResult — not "CareerAssessment"
— while the collection itself remains named career_assessments per
Section 4.1's table.
"""
from datetime import datetime, timezone
from enum import Enum

from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field


class AssessmentType(str, Enum):
    """
    The fixed set of assessment types named in architecture doc Section
    4.1. A str Enum, not free text, so an invalid type is rejected at
    validation time — same reasoning as VaultItemType (M2) and
    SkillCategory (M3).
    """
    APTITUDE = "aptitude"
    PERSONALITY = "personality"
    INTEREST = "interest"
    COMBINED = "combined"


class AssessmentResponseItem(BaseModel):
    """
    Embedded record of a user's raw answer to one assessment question.
    Not a Beanie Document — always read/written as part of its parent
    AssessmentAttempt.responses list, never queried independently, same
    pattern as SkillSignalSource being embedded inside UserSkillProfile
    in Milestone 3.

    `response` is typed as a plain string rather than something more
    specific: no question-bank model exists yet to define what a valid
    response looks like per question (see design notes above) — this
    field stores whatever raw answer was submitted (a selected option, a
    scale value, free text), uniformly.
    """

    question_id: str
    response: str


class AssessmentResult(BaseModel):
    """
    Embedded record of the AI-interpreted outcome of an assessment
    attempt. Field names match architecture doc Section 4.1's own
    description of this sub-object exactly.

    Not a Beanie Document — always read/written as part of its parent
    AssessmentAttempt. Nothing in this file computes these values; that
    is the assessment_interpretation AI touchpoint (Section 7.1),
    implemented in a later step of this milestone.
    """

    trait_scores: dict[str, float] = Field(default_factory=dict)
    recommended_domains: list[str] = Field(default_factory=list)
    summary: str | None = None


class AssessmentAttempt(Document):
    """
    A single user's attempt at a Career Assessment. One document per
    attempt — a user may have multiple AssessmentAttempt documents over
    time (retakes), unlike UserSkillProfile's one-per-user constraint in
    Milestone 3.
    """

    # Indexed (per architecture doc Section 4.5's "user_id indexed on
    # every user-scoped collection" rule), but deliberately NOT unique —
    # see design notes above.
    user_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]

    assessment_type: AssessmentType

    responses: list[AssessmentResponseItem] = Field(default_factory=list)

    # None until the assessment_interpretation AI touchpoint (a later
    # step) computes it. result is None -> not yet interpreted;
    # result is set -> interpretation complete. No separate status field
    # is needed to represent that distinction.
    result: AssessmentResult | None = None

    # ASSUMPTION (flagged in design notes above): architecture doc
    # Section 4.1 lists only completed_at. created_at is added here,
    # non-nullable and defaulted at construction (matching every other
    # model in this codebase), to distinguish "attempt started" from
    # "attempt completed" — completed_at alone cannot represent an
    # in-progress attempt.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Nullable: None means the attempt is still in progress (responses
    # may still be added). Set once the user finishes submitting
    # responses — that transition is a service-layer concern for a
    # later step, not this model's.
    completed_at: datetime | None = None

    class Settings:
        # Explicit collection name, matching architecture doc Section
        # 4.1 exactly — not left to Beanie's default
        # lowercased-classname behavior (which would otherwise produce
        # "assessmentattempt", not "career_assessments").
        name = "career_assessments"