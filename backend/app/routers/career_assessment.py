"""
PURPOSE
-------
HTTP layer for Career Assessment endpoints (Milestone 4). Per the Router
-> Service -> Repository -> Model architecture, this file contains NO
business logic, NO trait-score calculation, NO AI interpretation, NO
career recommendations, and NEVER queries Beanie directly — it only
parses requests (via schemas from app.schemas.career_assessment), calls
exactly one CareerAssessmentService method per endpoint, and returns the
result.

PUT vs PATCH on the /responses sub-resource is a deliberate HTTP-semantics
choice (see accompanying explanation): PUT maps to submit_responses
(first recording), PATCH maps to update_responses (correction) — both
service methods are functionally full-replacement today, but represent
distinct points in an attempt's lifecycle per Step 4/5's design.
"""
from fastapi import APIRouter, Depends, status

from app.dependencies.auth import get_current_user
from app.repositories.career_assessment_repository import CareerAssessmentRepository
from app.schemas.career_assessment import (
    AssessmentAttemptCreateRequest,
    AssessmentAttemptListResponse,
    AssessmentAttemptPublic,
    AssessmentResponsesSubmitRequest,
    AssessmentResponsesUpdateRequest,
)
from app.services.career_assessment_service import CareerAssessmentService

router = APIRouter(
    prefix="/career-assessments",
    tags=["Career Assessment"],
)


def get_career_assessment_service() -> CareerAssessmentService:
    """
    Provides a CareerAssessmentService instance, wired to a fresh
    CareerAssessmentRepository. Defined inline in this router file,
    matching the established pattern from app/routers/career_vault.py
    (M2) and app/routers/skill.py (M3) — not app/dependencies/, which is
    reserved for genuinely cross-cutting dependencies like
    get_current_user.
    """
    return CareerAssessmentService(CareerAssessmentRepository())


@router.post("", response_model=AssessmentAttemptPublic, status_code=status.HTTP_201_CREATED)
async def create_attempt(
    payload: AssessmentAttemptCreateRequest,
    current_user=Depends(get_current_user),
    assessment_service: CareerAssessmentService = Depends(get_career_assessment_service),
) -> AssessmentAttemptPublic:
    """
    Starts a new, empty assessment attempt for the authenticated user.
    """
    return await assessment_service.create_attempt(
        user_id=current_user.id,
        assessment_type=payload.assessment_type,
    )


@router.get("", response_model=AssessmentAttemptListResponse)
async def list_attempts(
    current_user=Depends(get_current_user),
    assessment_service: CareerAssessmentService = Depends(get_career_assessment_service),
) -> AssessmentAttemptListResponse:
    """
    Lists all assessment attempts belonging to the authenticated user —
    their complete attempt history, including retakes. An empty list is
    a normal outcome, never an error.
    """
    return await assessment_service.list_attempts(user_id=current_user.id)


@router.get("/{attempt_id}", response_model=AssessmentAttemptPublic)
async def get_attempt(
    attempt_id: str,
    current_user=Depends(get_current_user),
    assessment_service: CareerAssessmentService = Depends(get_career_assessment_service),
) -> AssessmentAttemptPublic:
    """
    Retrieves a single assessment attempt by id, scoped to the
    authenticated user.

    Raises:
        AssessmentAttemptNotFoundError (-> HTTP 404, via the global
            handler): if no matching attempt exists for this user.
    """
    return await assessment_service.get_attempt(attempt_id=attempt_id, user_id=current_user.id)


@router.put("/{attempt_id}/responses", response_model=AssessmentAttemptPublic)
async def submit_responses(
    attempt_id: str,
    payload: AssessmentResponsesSubmitRequest,
    current_user=Depends(get_current_user),
    assessment_service: CareerAssessmentService = Depends(get_career_assessment_service),
) -> AssessmentAttemptPublic:
    """
    Records the first full set of responses against an in-progress
    attempt. PUT semantics: puts this complete response set in place.

    Raises:
        AssessmentAttemptNotFoundError (-> HTTP 404, via the global
            handler): if no matching attempt exists for this user.
        AssessmentAlreadyCompletedError (-> HTTP 409, via the global
            handler): if the attempt already has a result.
    """
    return await assessment_service.submit_responses(
        attempt_id=attempt_id,
        user_id=current_user.id,
        responses=payload.responses,
    )


@router.patch("/{attempt_id}/responses", response_model=AssessmentAttemptPublic)
async def update_responses(
    attempt_id: str,
    payload: AssessmentResponsesUpdateRequest,
    current_user=Depends(get_current_user),
    assessment_service: CareerAssessmentService = Depends(get_career_assessment_service),
) -> AssessmentAttemptPublic:
    """
    Corrects previously-recorded responses on an attempt that has not
    yet been completed. PATCH semantics: modifies the existing resource.

    Raises:
        AssessmentAttemptNotFoundError (-> HTTP 404, via the global
            handler): if no matching attempt exists for this user.
        AssessmentAlreadyCompletedError (-> HTTP 409, via the global
            handler): if the attempt already has a result.
    """
    return await assessment_service.update_responses(
        attempt_id=attempt_id,
        user_id=current_user.id,
        responses=payload.responses,
    )


@router.delete("/{attempt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attempt(
    attempt_id: str,
    current_user=Depends(get_current_user),
    assessment_service: CareerAssessmentService = Depends(get_career_assessment_service),
) -> None:
    """
    Deletes an assessment attempt, scoped to the authenticated user.
    Returns HTTP 204 with no body on success.

    Raises:
        AssessmentAttemptNotFoundError (-> HTTP 404, via the global
            handler): if no matching attempt exists for this user.
    """
    await assessment_service.delete_attempt(attempt_id=attempt_id, user_id=current_user.id)