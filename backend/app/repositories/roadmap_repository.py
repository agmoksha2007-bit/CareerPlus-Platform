"""
PURPOSE
-------
Data access layer for the Roadmaps aggregate. This is the ONLY file
(besides app/core/database.py, which just registers the models) that
queries app.models.roadmap.RoadmapTemplate or
app.models.roadmap.UserRoadmapProgress directly.

Contains NO business logic: no enrollment rules, no milestone completion
rules, no roadmap generation, no progress calculations, no validation
beyond graceful handling of a malformed id. Both template management and
per-user progress tracking live in one class here, matching how both
Documents were defined together in one roadmap.py model file (Step 2) —
they're two collections belonging to the same bounded context.
"""
from beanie import PydanticObjectId

from app.models.roadmap import RoadmapTemplate, UserRoadmapProgress


class RoadmapRepository:
    """
    Data access for both roadmap_templates (platform-curated, no
    user_id) and user_roadmap_progress (per-user). Every user-scoped
    method here queries by user_id at the query level — same
    deliberate security property as every prior repository in this
    codebase.
    """

    # ------------------------------------------------------------------
    # Template methods
    # ------------------------------------------------------------------

    async def create_template(self, template: RoadmapTemplate) -> RoadmapTemplate:
        """
        Inserts an already-constructed RoadmapTemplate into MongoDB.
        Accepts the Document instance directly, matching this step's
        explicit requirement and the same pattern established in
        CareerGuidanceRepository.create (Step 4) — constructing the
        template's content is a service/content-authoring concern, not
        this method's.
        """
        await template.insert()
        return template

    async def get_template_by_id(self, template_id: str) -> RoadmapTemplate | None:
        """
        Fetches a single template by id. Returns None for both a
        malformed id and a genuinely missing document — same
        indistinguishable-at-this-layer pattern used by every prior
        repository's get_by_id.
        """
        try:
            object_id = PydanticObjectId(template_id)
        except Exception:
            return None
        return await RoadmapTemplate.get(object_id)

    async def list_templates(self) -> list[RoadmapTemplate]:
        """
        Returns every roadmap template, sorted alphabetically by title —
        a reasonable default for browsing platform-curated content,
        matching this step's explicit requirement (unlike most prior
        list methods in this codebase, which default to
        newest-first/created_at ordering, since templates have no
        natural "recency" the way user-generated records do).
        """
        return await RoadmapTemplate.find_all().sort(+RoadmapTemplate.title).to_list()

    # ------------------------------------------------------------------
    # User progress methods
    # ------------------------------------------------------------------

    async def create_progress(self, progress: UserRoadmapProgress) -> UserRoadmapProgress:
        """
        Inserts an already-constructed UserRoadmapProgress into MongoDB.
        Same accept-the-instance-directly pattern as create_template
        above — deciding WHEN a user enrolls in a roadmap (and
        constructing the initial milestone_status list) is a
        service-layer decision, not this method's.
        """
        await progress.insert()
        return progress

    async def get_progress_by_id(self, progress_id: str) -> UserRoadmapProgress | None:
        """
        Fetches a single progress record by id. Returns None for both a
        malformed id and a genuinely missing document.
        """
        try:
            object_id = PydanticObjectId(progress_id)
        except Exception:
            return None
        return await UserRoadmapProgress.get(object_id)

    async def get_progress_for_user(
        self, user_id: PydanticObjectId
    ) -> list[UserRoadmapProgress]:
        """
        Returns every progress record belonging to a user — across all
        roadmaps they're enrolled in (or have enrolled in previously,
        per Step 2's flagged non-unique-index assumption).
        """
        return await UserRoadmapProgress.find(UserRoadmapProgress.user_id == user_id).to_list()

    async def get_progress_for_user_and_template(
        self, user_id: PydanticObjectId, roadmap_template_id: PydanticObjectId
    ) -> UserRoadmapProgress | None:
        """
        Returns the progress record matching this specific user +
        template pair, or None if the user has no progress against this
        particular template. Note: per Step 2's flagged assumption that
        (user_id, roadmap_template_id) is not enforced unique, if
        multiple progress records existed for the same pair, this
        returns whichever one Beanie/MongoDB's find_one happens to
        return first — deciding how to handle that ambiguity (e.g.
        "most recent") is a service-layer concern if it ever becomes
        relevant, not this method's.
        """
        return await UserRoadmapProgress.find_one(
            UserRoadmapProgress.user_id == user_id,
            UserRoadmapProgress.roadmap_template_id == roadmap_template_id,
        )

    async def save_progress(self, progress: UserRoadmapProgress) -> UserRoadmapProgress:
        """
        Persists the latest in-memory state of an existing
        UserRoadmapProgress document via save(). Accepts the (already
        mutated) document directly — the service layer is responsible
        for loading a progress record, changing its milestone_status
        list, and passing the same object back here; this method has no
        opinion on what changed or why.
        """
        await progress.save()
        return progress

    async def delete_progress(self, progress_id: str) -> bool:
        """
        Deletes a progress record by id. Returns True if a matching
        document was found and deleted, False if the id was malformed
        or no matching document existed — same found/not-found boolean
        pattern as every prior repository's delete method.
        """
        try:
            object_id = PydanticObjectId(progress_id)
        except Exception:
            return False

        progress = await UserRoadmapProgress.get(object_id)
        if progress is None:
            return False

        await progress.delete()
        return True