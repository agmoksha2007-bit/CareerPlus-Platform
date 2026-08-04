"""
PURPOSE
-------
Data access layer for the Career Guidance aggregate. This is the ONLY file
(besides app/core/database.py, which just registers the model) that
queries app.models.career_guidance.GuidanceRecommendation directly.

Contains NO business logic: no generating recommendations, no interpreting
assessment results, no validation beyond graceful handling of a malformed
id. How a GuidanceRecommendation is CONSTRUCTED (the guidance_generation
AI touchpoint) is entirely a service-layer concern, a later step in this
milestone — this repository only persists and retrieves whatever
GuidanceRecommendation object it is given or asked for.
"""
from beanie import PydanticObjectId

from app.models.career_guidance import GuidanceRecommendation


class CareerGuidanceRepository:
    """
    Data access for the career_guidance_recommendations collection.
    Every read method is scoped by user_id where relevant, at the query
    level — same deliberate security property as every prior repository
    in this codebase.
    """

    async def create(self, recommendation: GuidanceRecommendation) -> GuidanceRecommendation:
        """
        Inserts an already-constructed GuidanceRecommendation into
        MongoDB. Unlike prior repositories' create() methods (which
        accepted individual fields and constructed the Document
        internally), this one accepts the Document instance directly —
        matching this step's explicit requirement. Constructing that
        instance (including running guidance_generation) is the
        service layer's job, not this method's.
        """
        await recommendation.insert()
        return recommendation

    async def get_by_id(self, recommendation_id: str) -> GuidanceRecommendation | None:
        """
        Fetches a single recommendation by id. Returns None for both a
        malformed id and a genuinely missing document — same
        indistinguishable-at-this-layer pattern used by every prior
        repository's get_by_id, so callers only ever need to handle one
        case (None).
        """
        try:
            object_id = PydanticObjectId(recommendation_id)
        except Exception:
            return None
        return await GuidanceRecommendation.get(object_id)

    async def list_for_user(self, user_id: PydanticObjectId) -> list[GuidanceRecommendation]:
        """
        Returns all recommendations generated for a user, newest first
        (descending created_at) — same default ordering convention as
        every prior repository's list method (e.g.
        CareerAssessmentRepository.list_by_user, Milestone 4).
        """
        return (
            await GuidanceRecommendation.find(GuidanceRecommendation.user_id == user_id)
            .sort(-GuidanceRecommendation.created_at)
            .to_list()
        )

    async def get_latest_for_user(
        self, user_id: PydanticObjectId
    ) -> GuidanceRecommendation | None:
        """
        Returns the single newest recommendation for a user, or None if
        the user has none yet — a normal outcome (e.g. before their
        first guidance-generation run), not an error condition.
        """
        return (
            await GuidanceRecommendation.find(GuidanceRecommendation.user_id == user_id)
            .sort(-GuidanceRecommendation.created_at)
            .first_or_none()
        )

    async def delete(self, recommendation_id: str) -> bool:
        """
        Deletes a recommendation by id. Returns True if a matching
        document was found and deleted, False if the id was malformed
        or no matching document existed — same found/not-found boolean
        pattern as every prior repository's delete method.
        """
        try:
            object_id = PydanticObjectId(recommendation_id)
        except Exception:
            return False

        recommendation = await GuidanceRecommendation.get(object_id)
        if recommendation is None:
            return False

        await recommendation.delete()
        return True