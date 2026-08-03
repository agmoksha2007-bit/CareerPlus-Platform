"""
PURPOSE
-------
API request/response contracts for Career Assessment (Milestone 4,
architecture doc Section 4.1). This file contains ONLY Pydantic schemas —
no database queries, no business rules, no AI interpretation, no career
recommendation logic. How a submitted response list becomes a
trait-scored, domain-recommended AssessmentResult is entirely a service-
layer concern (app/services/career_assessment_service.py, a later step),
never this file's.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.career_assessment import AssessmentType

# ======================================================================
# Request schemas
# ======================================================================


class AssessmentAttemptCreateRequest(BaseModel):
    """
    Request body for starting a new assessment attempt. Used by the
    router (a later step), passed into
    CareerAssessmentService.create_attempt(...).

    No responses are accepted at creation time — matching
    AssessmentAttempt's design (Step 1): an attempt always starts empty,
    with responses recorded afterward via a separate submit call.
    """

    assessment_type: AssessmentType


class AssessmentResponseItemInput(BaseModel):
    """
    One raw answer to one assessment question, as submitted by a client.
    Embedded inside the two request schemas below — not used standalone.

    `response` is a plain, length-bounded string, deliberately not typed
    more specifically: no question-bank model exists yet to define what
    a valid answer looks like per question (same reasoning recorded in
    AssessmentResponseItem's own docstring at the model layer, Step 1).
    This schema can only validate that SOMETHING non-blank was submitted
    — not that it's the RIGHT kind of answer for that question.
    """

    question_id: str = Field(min_length=1, max_length=100)
    response: str = Field(min_length=1, max_length=2000)

    @field_validator("question_id", "response")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        """Same non-blank-after-strip pattern used throughout this codebase."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank")
        return stripped


class AssessmentResponsesSubmitRequest(BaseModel):
    """
    Request body for recording a batch of responses against an existing,
    in-progress attempt. Used by the router, passed into
    CareerAssessmentService.submit_responses(...).

    Represents a COMPLETE replacement of the attempt's responses list —
    see design notes above for why per-item merging is deliberately not
    handled at this layer.
    """

    responses: list[AssessmentResponseItemInput] = Field(min_length=1)


class AssessmentResponsesUpdateRequest(BaseModel):
    """
    Request body for correcting previously-recorded responses on an
    attempt that has not yet been completed. Used by the router, passed
    into CareerAssessmentService.update_responses(...).

    Structurally identical to AssessmentResponsesSubmitRequest, but kept
    as a separate schema deliberately (see design notes above) — they
    represent different points in an attempt's lifecycle and may need to
    diverge independently later.
    """

    responses: list[AssessmentResponseItemInput] = Field(min_length=1)


# ======================================================================
# Response schemas
# ======================================================================


class AssessmentResponseItemPublic(BaseModel):
    """
    Response shape for one recorded response, embedded inside
    AssessmentAttemptPublic.responses. Mirrors
    app.models.career_assessment.AssessmentResponseItem's fields exactly,
    kept as a separate schema rather than reusing the model directly —
    consistent with every other model/schema split in this codebase.
    """

    question_id: str
    response: str

    model_config = ConfigDict(from_attributes=True)


class AssessmentResultPublic(BaseModel):
    """
    Response shape for an attempt's interpreted result. Field names
    mirror app.models.career_assessment.AssessmentResult exactly. All
    fields default to their "not yet computed" state (empty
    dict/list, None summary) — matching the model's own defaults from
    Step 1 — since a result can be embedded in a response before AI
    interpretation (a later step) has produced a complete result.
    """

    trait_scores: dict[str, float] = Field(default_factory=dict)
    recommended_domains: list[str] = Field(default_factory=list)
    summary: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AssessmentAttemptPublic(BaseModel):
    """
    Response shape for a single assessment attempt — returned by
    create/get/submit/update endpoints alike, same one-schema-per-
    resource pattern as CareerVaultItemPublic (M2) and
    SkillTaxonomyPublic (M3).

    `result` is nullable, directly mirroring AssessmentAttempt.result:
    None means not yet interpreted; this is a normal, expected state for
    an in-progress attempt, not an error.
    """

    id: str
    assessment_type: AssessmentType
    responses: list[AssessmentResponseItemPublic]
    result: AssessmentResultPublic | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AssessmentAttemptListResponse(BaseModel):
    """
    Response shape for the list-attempts endpoint (a later step). Wraps
    the attempt list with a `total` count, rather than the router
    returning a bare list[AssessmentAttemptPublic] — a deliberate
    departure from M2/M3's list-endpoint convention, included because it
    was explicitly requested as its own schema for this milestone.
    """

    attempts: list[AssessmentAttemptPublic]
    total: int = Field(ge=0)