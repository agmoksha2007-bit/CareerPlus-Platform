"""
PURPOSE
-------
HTTP layer for Roadmaps endpoints (Milestone 5). Per the Router -> Service
-> Repository -> Model architecture, this file contains NO business logic
and NEVER queries Beanie or the repository directly — it only parses
requests, calls exactly one RoadmapService method per endpoint, and shapes
the result into a response schema.

RoadmapService's methods (Step 10) return raw RoadmapTemplate /
UserRoadmapProgress Document instances, not pre-shaped response schemas —
same situation as career_guidance.py (Step 11). The private _to_*_response
helpers below perform that mapping, which is response-shaping, not a
business rule.
"""
from fastapi import APIRouter, Depends, status

from app.dependencies.auth import get_current_user
from app.models.roadmap import RoadmapTemplate, UserRoadmapProgress
from app.repositories.roadmap_repository import RoadmapRepository
from app.schemas.roadmap import (
    MilestoneStatusResponse,
    RoadmapEnrollmentRequest,
    RoadmapMilestoneResponse,
    RoadmapTemplateListResponse,
    RoadmapTemplateResponse,
    UserRoadmapProgressListResponse,
    UserRoadmapProgressResponse,
)
from app.services.roadmap_service import RoadmapService

router = APIRouter(
    prefix="/api/v1/roadmaps",
    tags=["Roadmaps"],
)


def get_roadmap_service() -> RoadmapService:
    """
    Provides a RoadmapService instance, wired to a fresh
    RoadmapRepository. Defined inline in this router file, matching the
    established pattern from career_vault.py (M2), skill.py (M3),
    career_assessment.py (M4), and career_guidance.py (M5, Step 11) —
    not app/dependencies/, which is reserved for genuinely cross-cutting
    dependencies like get_current_user.
    """
    return RoadmapService(RoadmapRepository())


def _to_template_response(template: RoadmapTemplate) -> RoadmapTemplateResponse:
    """
    Maps a RoadmapTemplate Document to the API-facing
    RoadmapTemplateResponse schema — id converted to str, embedded
    RoadmapMilestone entries mapped to RoadmapMilestoneResponse. Plain
    attribute copying only; no decision-making happens here.
    """
    return RoadmapTemplateResponse(
        id=str(template.id),
        title=template.title,
        description=template.description,
        milestones=[
            RoadmapMilestoneResponse(
                order=milestone.order,
                title=milestone.title,
                description=milestone.description,
                linked_module=milestone.linked_module,
                linked_resource_id=milestone.linked_resource_id,
            )
            for milestone in template.milestones
        ],
    )


def _to_progress_response(progress: UserRoadmapProgress) -> UserRoadmapProgressResponse:
    """
    Maps a UserRoadmapProgress Document to the API-facing
    UserRoadmapProgressResponse schema — id fields converted to str,
    embedded MilestoneStatus entries mapped to MilestoneStatusResponse.
    Plain attribute copying only.
    """
    return UserRoadmapProgressResponse(
        id=str(progress.id),
        user_id=str(progress.user_id),
        roadmap_template_id=str(progress.roadmap_template_id),
        milestone_status=[
            MilestoneStatusResponse(
                milestone_order=status_entry.milestone_order,
                status=status_entry.status,
                completed_at=status_entry.completed_at,
            )
            for status_entry in progress.milestone_status
        ],
    )


@router.get("/", response_model=RoadmapTemplateListResponse)
async def list_templates(
    current_user=Depends(get_current_user),
    roadmap_service: RoadmapService = Depends(get_roadmap_service),
) -> RoadmapTemplateListResponse:
    """
    Returns every roadmap template. Templates are platform-curated
    content with no owning user, so this list is the same for every
    authenticated caller.
    """
    templates = await roadmap_service.list_templates()
    return RoadmapTemplateListResponse(
        roadmaps=[_to_template_response(template) for template in templates]
    )


@router.post("/enroll", response_model=UserRoadmapProgressResponse, status_code=status.HTTP_201_CREATED)
async def enroll_user(
    payload: RoadmapEnrollmentRequest,
    current_user=Depends(get_current_user),
    roadmap_service: RoadmapService = Depends(get_roadmap_service),
) -> UserRoadmapProgressResponse:
    """
    Enrolls the authenticated user into a roadmap template, creating a
    new progress record with an empty milestone_status list.

    Registered as a distinct literal path (/enroll) — no ordering
    conflict with /{template_id} since this is a POST, not a GET.

    Raises:
        RoadmapTemplateNotFoundError (-> HTTP 404, via the global
            handler): if roadmap_template_id does not refer to an
            existing template.
        RoadmapEnrollmentError (-> HTTP 400, via the global handler):
            if persistence fails unexpectedly after the template
            existence check passes.
    """
    progress = await roadmap_service.enroll_user(
        user_id=current_user.id,
        roadmap_template_id=payload.roadmap_template_id,
    )
    return _to_progress_response(progress)


@router.get("/progress", response_model=UserRoadmapProgressListResponse)
async def get_user_progress(
    current_user=Depends(get_current_user),
    roadmap_service: RoadmapService = Depends(get_roadmap_service),
) -> UserRoadmapProgressListResponse:
    """
    Returns all roadmap progress records for the authenticated user,
    across every roadmap they're enrolled in. Registered BEFORE
    /{template_id} so "progress" is never captured as a template_id
    path parameter. An empty list is a normal outcome, never an error.
    """
    progress_records = await roadmap_service.get_user_progress(current_user.id)
    return UserRoadmapProgressListResponse(
        progress=[_to_progress_response(record) for record in progress_records]
    )


@router.get("/progress/{progress_id}", response_model=UserRoadmapProgressResponse)
async def get_progress(
    progress_id: str,
    current_user=Depends(get_current_user),
    roadmap_service: RoadmapService = Depends(get_roadmap_service),
) -> UserRoadmapProgressResponse:
    """
    Returns a single progress record by id. Registered BEFORE
    /{template_id} for the same route-ordering reason as
    /progress above.

    NOTE: per RoadmapService.get_progress()'s spec (Step 10), this
    lookup is NOT scoped to current_user — any authenticated user can
    fetch any progress record by id if they know it. current_user is
    still required (authentication is enforced), but ownership is not.
    Same flagged gap as career_guidance.py's get_recommendation
    endpoint (Step 11).

    Raises:
        RoadmapProgressNotFoundError (-> HTTP 404, via the global
            handler): if no progress record exists for this id.
    """
    progress = await roadmap_service.get_progress(progress_id)
    return _to_progress_response(progress)


@router.get("/{template_id}", response_model=RoadmapTemplateResponse)
async def get_template(
    template_id: str,
    current_user=Depends(get_current_user),
    roadmap_service: RoadmapService = Depends(get_roadmap_service),
) -> RoadmapTemplateResponse:
    """
    Returns a single roadmap template by id. Registered LAST among the
    GET routes on this router so it never shadows the more specific
    /progress and /progress/{progress_id} paths above.

    Raises:
        RoadmapTemplateNotFoundError (-> HTTP 404, via the global
            handler): if no template exists for this id.
    """
    template = await roadmap_service.get_template(template_id)
    return _to_template_response(template)