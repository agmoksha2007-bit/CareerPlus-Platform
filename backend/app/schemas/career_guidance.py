"""
PURPOSE
-------
API request/response contracts for Career Guidance (Milestone 5,
architecture doc Section 4.2). This file contains ONLY Pydantic schemas —
no database queries, no business logic, no AI generation logic. How a
GuidanceRecommendation is actually PRODUCED (the guidance_generation AI
touchpoint, Section 7.1) is entirely a service-layer concern
(app/services/career_guidance_service.py, a later step), never this
file's.

Kept completely separate from app.models.career_guidance: the Beanie
Document there represents database storage; these schemas represent the
HTTP contract — same split as every prior schema file in this codebase.
No Beanie imports here at all (not even PydanticObjectId) — every id in
these schemas is a plain string, converted at the service-layer boundary,
consistent with every other schema file's convention (e.g.
CareerVaultItemPublic.id: str, AssessmentAttemptPublic.id: str).
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RecommendedPathResponse(BaseModel):
    """
    Response shape for one recommended career path, embedded inside
    GuidanceRecommendationResponse.recommended_paths. Mirrors
    app.models.career_guidance.RecommendedPath's fields exactly, kept as
    a separate schema rather than reusing the model directly — same
    model/schema split used throughout this codebase.
    """

    path_name: str
    rationale: str
    confidence: float

    model_config = ConfigDict(from_attributes=True)


class GuidanceRecommendationResponse(BaseModel):
    """
    Response shape for a single stored recommendation — returned by
    generate/get/list endpoints alike, same one-schema-per-resource
    pattern as every prior *Public response schema in this codebase.

    based_on_assessment_id is nullable, directly mirroring
    GuidanceRecommendation.based_on_assessment_id: None means this
    recommendation was not generated from a specific assessment attempt.
    """

    id: str
    user_id: str
    based_on_assessment_id: str | None
    recommended_paths: list[RecommendedPathResponse]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GuidanceGenerationRequest(BaseModel):
    """
    Request body for generating new guidance. assessment_id is Optional
    — per architecture doc Section 4.2 and this milestone's own model
    design (Step 1), a recommendation does not necessarily require an
    assessment to base itself on.

    No custom validators: assessment_id is a plain optional string here.
    Verifying that a supplied assessment_id actually refers to a real,
    owned AssessmentAttempt is a business rule (requires a database
    lookup against a DIFFERENT aggregate, CareerAssessmentRepository) —
    that check belongs to the service layer, a later step, not this
    schema.
    """

    assessment_id: str | None = None


class GuidanceRecommendationListResponse(BaseModel):
    """
    Response shape for the list-recommendations endpoint (a later
    step). Wraps the recommendation list in a named field, same
    wrapped-list convention as AssessmentAttemptListResponse
    (Milestone 4), rather than a bare list[GuidanceRecommendationResponse].
    """

    recommendations: list[GuidanceRecommendationResponse]