"""
PURPOSE
-------
Beanie document schema for the `career_guidance_recommendations`
collection — Milestone 5's Career Guidance sub-module (architecture doc
Section 4.2, Group B: Direction).

This is the persistence layer only. HOW a recommendation is generated —
the guidance_generation AI touchpoint (architecture doc Section 7.1),
which reads Career Assessment output and Skills Engine profile data — is
a future service-layer step in this same milestone, not this file's job.
This model only defines the shape a generated recommendation is stored in.
"""
from datetime import datetime, timezone

from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field


class RecommendedPath(BaseModel):
    """
    Embedded record of one recommended career path within a
    GuidanceRecommendation. Field names match architecture doc Section
    4.2's own description exactly: {path_name, rationale, confidence}.

    Not a Beanie Document — always read/written as part of its parent
    GuidanceRecommendation.recommended_paths list, never queried
    independently, same embedding pattern as every prior milestone's
    embedded sub-models (e.g. RecommendedPath here mirrors how
    AssessmentResponseItem is embedded inside AssessmentAttempt, M4).
    """

    path_name: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=2000)

    # Bounded 0.0-1.0, same range convention as UserSkillEntry.confidence
    # (Milestone 3) — how confident the guidance-generation process is in
    # this specific path recommendation, distinct from how STRONG the
    # recommendation is worded (rationale).
    confidence: float = Field(ge=0.0, le=1.0)


class GuidanceRecommendation(Document):
    """
    A single generated set of career-path recommendations for a user.
    One document per generation run — a user may have multiple
    GuidanceRecommendation documents over time (e.g. after retaking an
    assessment), unlike UserSkillProfile's one-per-user constraint
    (Milestone 3).
    """

    # Indexed (per architecture doc Section 4.5's "user_id indexed on
    # every user-scoped collection" rule), but deliberately NOT unique —
    # same reasoning as AssessmentAttempt.user_id (Milestone 4).
    user_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]

    # Traces this recommendation back to the specific assessment attempt
    # that informed it (architecture doc Section 4.2: "traceability back
    # to the assessment"). Typed as PydanticObjectId, not a generic str
    # (unlike SkillSignalSource.reference_id in Milestone 3), because the
    # relationship to AssessmentAttempt is explicitly known — see design
    # notes above. Nullable: the architecture doc does not state every
    # recommendation must originate from an assessment.
    based_on_assessment_id: PydanticObjectId | None = None

    recommended_paths: list[RecommendedPath] = Field(default_factory=list)

    # No updated_at: a recommendation is the point-in-time OUTPUT of one
    # guidance-generation run, not a user-editable resource. Updated
    # guidance means generating a NEW recommendation, not editing this
    # one — a future service-layer decision, not a field this model
    # needs to support in-place edits.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        # Explicit collection name, matching architecture doc Section
        # 4.2 exactly.
        name = "career_guidance_recommendations"