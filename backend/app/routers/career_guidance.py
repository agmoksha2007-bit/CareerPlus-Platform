"""
PURPOSE
-------
HTTP layer for Career Guidance endpoints (Milestone 5). Per the Router ->
Service -> Repository -> Model architecture, this file contains NO
business logic and NEVER queries Beanie or the repository directly — it
only parses requests, calls exactly one CareerGuidanceService method per
endpoint, and shapes the result into a response schema.

CareerGuidanceService's methods (Step 9) return raw GuidanceRecommendation
Document instances, not pre-shaped response schemas — unlike every prior
milestone's service layer. The private _to_response helper below performs
that mapping (id -> str, etc.), which is response-shaping, not a business
rule, matching the same reasoning used for the explicit UserPublic
construction in GET /users/me (Milestone 1).
"""
from fastapi import APIRouter, Depends, status

from app.dependencies.auth import get_current_user
from app.models.career_guidance import GuidanceRecommendation
from app.repositories.career_guidance_repository import CareerGuidanceRepository
from app.schemas.career_guidance import (
    GuidanceGenerationRequest,
    GuidanceRecommendationListResponse,
    GuidanceRecommendationResponse,
    RecommendedPathResponse,
)
from app.services.career_guidance_service import CareerGuidanceService

router = APIRouter(
    prefix="/api/v1/career-guidance",
    tags=["Career Guidance"],
)


def get_career_guidance_service() -> CareerGuidanceService:
    """
    Provides a CareerGuidanceService instance, wired to a fresh
    CareerGuidanceRepository. Defined inline in this router file,
    matching the established pattern from career_vault.py (M2),
    skill.py (M3), and career_assessment.py (M4) — not
    app/dependencies/, which is reserved for genuinely cross-cutting
    dependencies like get_current_user.
    """
    return CareerGuidanceService(CareerGuidanceRepository())


def _to_response(recommendation: GuidanceRecommendation) -> GuidanceRecommendationResponse:
    """
    Maps a GuidanceRecommendation Document to the API-facing
    GuidanceRecommendationResponse schema — id fields converted to str,
    embedded RecommendedPath entries mapped to RecommendedPathResponse.
    Plain attribute copying only; no decision-making happens here.
    """
    return GuidanceRecommendationResponse(
        id=str(recommendation.id),
        user_id=str(recommendation.user_id),
        based_on_assessment_id=(
            str(recommendation.based_on_assessment_id)
            if recommendation.based_on_assessment_id is not None
            else None
        ),
        recommended_paths=[
            RecommendedPathResponse(
                path_name=path.path_name,
                rationale=path.rationale,
                confidence=path.confidence,
            )
            for path in recommendation.recommended_paths
        ],
        created_at=recommendation.created_at,
    )


@router.post("/", response_model=GuidanceRecommendationResponse, status_code=status.HTTP_201_CREATED)
async def generate_guidance(
    payload: GuidanceGenerationRequest,
    current_user=Depends(get_current_user),
    guidance_service: CareerGuidanceService = Depends(get_career_guidance_service),
) -> GuidanceRecommendationResponse:
    """
    Generates a new guidance recommendation for the authenticated user.

    Per CareerGuidanceService.generate_guidance()'s current scope
    (Step 9), this produces a PLACEHOLDER recommendation — no AI/LLM
    call happens yet.

    Raises:
        GuidanceGenerationError (-> HTTP 500, via the global handler):
            if assessment_id is malformed, or persistence fails
            unexpectedly.
    """
    recommendation = await guidance_service.generate_guidance(
        user_id=current_user.id,
        assessment_id=payload.assessment_id,
    )
    return _to_response(recommendation)


@router.get("/", response_model=GuidanceRecommendationListResponse)
async def list_user_recommendations(
    current_user=Depends(get_current_user),
    guidance_service: CareerGuidanceService = Depends(get_career_guidance_service),
) -> GuidanceRecommendationListResponse:
    """
    Returns all guidance recommendations generated for the authenticated
    user, newest first. An empty list is a normal outcome, never an
    error.
    """
    recommendations = await guidance_service.list_user_recommendations(current_user.id)
    return GuidanceRecommendationListResponse(
        recommendations=[_to_response(rec) for rec in recommendations]
    )


@router.get("/latest", response_model=GuidanceRecommendationResponse)
async def get_latest_recommendation(
    current_user=Depends(get_current_user),
    guidance_service: CareerGuidanceService = Depends(get_career_guidance_service),
) -> GuidanceRecommendationResponse:
    """
    Returns the authenticated user's single newest recommendation.
    Registered BEFORE /{recommendation_id} so "latest" is never
    captured as a recommendation_id path parameter.

    Raises:
        GuidanceRecommendationNotFoundError (-> HTTP 404, via the global
            handler): if the user has no recommendations yet.
    """
    recommendation = await guidance_service.get_latest_recommendation(current_user.id)
    return _to_response(recommendation)


@router.get("/{recommendation_id}", response_model=GuidanceRecommendationResponse)
async def get_recommendation(
    recommendation_id: str,
    current_user=Depends(get_current_user),
    guidance_service: CareerGuidanceService = Depends(get_career_guidance_service),
) -> GuidanceRecommendationResponse:
    """
    Returns a single recommendation by id.

    NOTE: per CareerGuidanceService.get_recommendation()'s spec
    (Step 9), this lookup is NOT scoped to current_user — any
    authenticated user can fetch any recommendation by id if they know
    it. current_user is still required (authentication is enforced),
    but ownership is not. Flagged in Step 9 and repeated here since this
    router is where that gap becomes externally visible.

    Raises:
        GuidanceRecommendationNotFoundError (-> HTTP 404, via the global
            handler): if no recommendation exists for this id.
    """
    recommendation = await guidance_service.get_recommendation(recommendation_id)
    return _to_response(recommendation)