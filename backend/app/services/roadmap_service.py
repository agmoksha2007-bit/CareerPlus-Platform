"""
PURPOSE
-------
Business logic for Roadmaps: listing/retrieving templates, enrolling users,
and retrieving/persisting progress. This layer depends ONLY on
RoadmapRepository — it never imports Beanie or
app.models.roadmap.RoadmapTemplate/UserRoadmapProgress's persistence
details directly beyond constructing the Document instances handed to the
repository's create_* methods.

Explicitly OUT OF SCOPE for this file, per Step 10: milestone-completion
rules (what makes a milestone "complete", how status transitions are
validated) are not implemented here — save_progress() persists whatever
UserRoadmapProgress state it is given, with no opinion on what changed.
"""
from beanie import PydanticObjectId

from app.core.exceptions import (
    RoadmapEnrollmentError,
    RoadmapProgressNotFoundError,
    RoadmapTemplateNotFoundError,
)
from app.models.roadmap import RoadmapTemplate, UserRoadmapProgress
from app.repositories.roadmap_repository import RoadmapRepository


class RoadmapService:
    """
    Orchestrates RoadmapRepository. Holds no state beyond the repository
    it's constructed with — cheap to create per-request, same pattern as
    every prior service.
    """

    def __init__(self, roadmap_repository: RoadmapRepository):
        self._roadmap_repo = roadmap_repository

    async def list_templates(self) -> list[RoadmapTemplate]:
        """
        Returns every roadmap template. Templates are platform-curated
        content with no owning user, so there is no user-scoping concern
        here — every caller sees the same full list.
        """
        return await self._roadmap_repo.list_templates()

    async def get_template(self, template_id: str) -> RoadmapTemplate:
        """
        Retrieves a single roadmap template by id.

        Raises:
            RoadmapTemplateNotFoundError: if no template exists for this
                id (whether malformed or genuinely missing — same
                indistinguishable-at-this-layer pattern used throughout
                this codebase).
        """
        template = await self._roadmap_repo.get_template_by_id(template_id)
        if template is None:
            raise RoadmapTemplateNotFoundError("Roadmap template not found")
        return template

    async def enroll_user(
        self, user_id: PydanticObjectId, roadmap_template_id: str
    ) -> UserRoadmapProgress:
        """
        Enrolls a user in a roadmap template by creating a new,
        empty-progress UserRoadmapProgress record.

        Business rules enforced here, in order:
        1. The referenced template must actually exist — verified via
           get_template_by_id before any progress record is created.
        2. milestone_status starts empty (per Step 10's explicit
           requirement) — this method does not pre-populate a
           not_started entry per milestone; that population, if wanted,
           is left for a future step to decide, not assumed here.

        Raises:
            RoadmapTemplateNotFoundError: if roadmap_template_id does
                not refer to an existing template.
            RoadmapEnrollmentError: if repository persistence fails
                unexpectedly after the template existence check passes.
        """
        template = await self._roadmap_repo.get_template_by_id(roadmap_template_id)
        if template is None:
            raise RoadmapTemplateNotFoundError("Roadmap template not found")

        try:
            new_progress = UserRoadmapProgress(
                user_id=user_id,
                roadmap_template_id=PydanticObjectId(roadmap_template_id),
                milestone_status=[],
            )
            return await self._roadmap_repo.create_progress(new_progress)
        except Exception as exc:
            raise RoadmapEnrollmentError(
                "Failed to enroll user in this roadmap"
            ) from exc

    async def get_user_progress(self, user_id: PydanticObjectId) -> list[UserRoadmapProgress]:
        """
        Returns every progress record belonging to a user, across all
        roadmaps they're enrolled in. An empty result (a user enrolled
        in nothing yet) is a normal outcome, never an error.
        """
        return await self._roadmap_repo.get_progress_for_user(user_id)

    async def get_progress(self, progress_id: str) -> UserRoadmapProgress:
        """
        Retrieves a single progress record by id.

        NOTE: per Step 10's explicit method spec, this takes ONLY
        progress_id — no user_id parameter, so ownership is not
        enforced at this method's boundary (see scope note above,
        consistent with Step 9's CareerGuidanceService.get_recommendation).

        Raises:
            RoadmapProgressNotFoundError: if no progress record exists
                for this id.
        """
        progress = await self._roadmap_repo.get_progress_by_id(progress_id)
        if progress is None:
            raise RoadmapProgressNotFoundError("Roadmap progress record not found")
        return progress

    async def save_progress(self, progress: UserRoadmapProgress) -> UserRoadmapProgress:
        """
        Persists the latest in-memory state of an existing
        UserRoadmapProgress document. Accepts the (already mutated)
        document directly, matching Step 10's explicit spec — this
        method has no opinion on what changed within milestone_status or
        why; milestone-completion rules are explicitly out of scope for
        this milestone.
        """
        return await self._roadmap_repo.save_progress(progress)