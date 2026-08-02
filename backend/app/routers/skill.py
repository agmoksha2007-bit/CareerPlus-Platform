"""
PURPOSE
-------
HTTP layer for Skills Engine endpoints (Milestone 3). Per the Router ->
Service -> Repository -> Model architecture, this file contains NO
business logic, NO scoring logic, NO skill normalization, and NEVER
queries Beanie directly — it only parses requests (via schemas from
app.schemas.skill), calls exactly one SkillsEngineService method per
endpoint, and returns the result.

record_signal is intentionally NOT exposed as an HTTP endpoint here — per
app/schemas/skill.py's own docstring, SkillSignalInput is an internal
contract whose primary callers are other services (in future milestones),
not a public HTTP request body.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.auth import get_current_user
from app.models.skill import SkillCategory
from app.repositories.skill_repository import SkillTaxonomyRepository, UserSkillProfileRepository
from app.schemas.skill import (
    SkillTaxonomyCreateRequest,
    SkillTaxonomyPublic,
    SkillTaxonomyUpdateRequest,
    UserSkillProfilePublic,
)
from app.services.skills_engine_service import SkillsEngineService

router = APIRouter(
    prefix="/skills",
    tags=["Skills"],
)


def get_skills_engine_service() -> SkillsEngineService:
    """
    Provides a SkillsEngineService instance, wired to fresh repository
    instances. Defined inline in this router file, matching the
    established pattern from app/routers/career_vault.py (Milestone 2) —
    not app/dependencies/, which is reserved for genuinely cross-cutting
    dependencies like get_current_user. Kept as a dependency provider
    (not instantiated inline in each endpoint) so it can be overridden
    with a fake service in tests, same reasoning as every other
    *_service provider in this codebase.
    """
    return SkillsEngineService(SkillTaxonomyRepository(), UserSkillProfileRepository())


@router.post("/taxonomy", response_model=SkillTaxonomyPublic, status_code=status.HTTP_201_CREATED)
async def create_taxonomy_entry(
    payload: SkillTaxonomyCreateRequest,
    current_user=Depends(get_current_user),
    skills_service: SkillsEngineService = Depends(get_skills_engine_service),
) -> SkillTaxonomyPublic:
    """
    Creates a new canonical skill in the platform taxonomy.

    Requires authentication only — this codebase has no role/permission
    system yet (flagged explicitly above and in Milestone 1), so any
    authenticated user can currently create taxonomy entries. That is a
    known gap, not a deliberate product decision, and not something this
    router invents a workaround for.

    Raises:
        SkillNameAlreadyExistsError (-> HTTP 409, via the global
            handler): if a taxonomy entry with this name already exists.
    """
    return await skills_service.create_taxonomy_entry(
        name=payload.name,
        category=payload.category,
        aliases=payload.aliases,
        related_skill_ids=payload.related_skill_ids,
    )


@router.patch("/taxonomy/{skill_id}", response_model=SkillTaxonomyPublic)
async def update_taxonomy_entry(
    skill_id: str,
    payload: SkillTaxonomyUpdateRequest,
    current_user=Depends(get_current_user),
    skills_service: SkillsEngineService = Depends(get_skills_engine_service),
) -> SkillTaxonomyPublic:
    """
    Applies a partial update to an existing taxonomy entry.
    exclude_unset=True ensures only fields the client actually sent are
    passed through — an omitted field is left untouched, same convention
    as CareerVaultService.update_item in Milestone 2.

    Raises:
        SkillTaxonomyEntryNotFoundError (-> HTTP 404, via the global
            handler): if no entry exists for this id.
    """
    updates = payload.model_dump(exclude_unset=True)
    return await skills_service.update_taxonomy_entry(skill_id, updates)


@router.get("/taxonomy/{skill_id}", response_model=SkillTaxonomyPublic)
async def get_taxonomy_entry(
    skill_id: str,
    current_user=Depends(get_current_user),
    skills_service: SkillsEngineService = Depends(get_skills_engine_service),
) -> SkillTaxonomyPublic:
    """
    Retrieves a single taxonomy entry by id.

    Raises:
        SkillTaxonomyEntryNotFoundError (-> HTTP 404, via the global
            handler): if no entry exists for this id.
    """
    return await skills_service.get_taxonomy_entry(skill_id)


@router.get("/taxonomy", response_model=list[SkillTaxonomyPublic])
async def list_or_search_taxonomy(
    q: str | None = Query(default=None, description="Search text, matched against name and aliases."),
    category: SkillCategory | None = Query(default=None, description="Filter to one skill category."),
    current_user=Depends(get_current_user),
    skills_service: SkillsEngineService = Depends(get_skills_engine_service),
) -> list[SkillTaxonomyPublic]:
    """
    Lists or searches taxonomy entries. Exactly one of `q` or `category`
    must be supplied:
      - `q` present -> dispatches to SkillsEngineService.search_taxonomy.
      - `category` present (and `q` absent) -> dispatches to
        SkillsEngineService.list_taxonomy_by_category.
      - Neither present -> HTTP 422. There is no "list every taxonomy
        entry unfiltered" method on the service (none was defined in
        Step 3 or Step 5), so this endpoint cannot silently fall back to
        one — this reflects an actual gap in what's been built, not an
        arbitrary restriction invented here.

    This if/elif dispatch is HTTP query-parameter routing (which read
    method matches the given parameters), not a domain rule — no data
    is validated or transformed beyond selecting which existing service
    method to call.
    """
    if q is not None:
        return await skills_service.search_taxonomy(q)
    if category is not None:
        return await skills_service.list_taxonomy_by_category(category)

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Provide either 'q' (search text) or 'category' to list taxonomy entries.",
    )


@router.get("/profile", response_model=UserSkillProfilePublic)
async def get_my_profile(
    current_user=Depends(get_current_user),
    skills_service: SkillsEngineService = Depends(get_skills_engine_service),
) -> UserSkillProfilePublic:
    """
    Retrieves the authenticated user's own skill profile. No path
    parameter — always scoped to current_user.id, same "always self,
    never an arbitrary id" pattern as GET /users/me in Milestone 1.

    Returns a synthesized empty profile (skills=[]) if the user has
    never triggered a skill signal yet — never a 404, per
    SkillsEngineService.get_profile's own documented behavior.
    """
    return await skills_service.get_profile(current_user.id)