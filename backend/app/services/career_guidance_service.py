"""
PURPOSE
-------
Business logic for Career Guidance: retrieving, listing, and generating
GuidanceRecommendation records. This layer depends ONLY on
CareerGuidanceRepository — it never imports Beanie or
app.models.career_guidance.GuidanceRecommendation's persistence details
directly beyond constructing the Document instance handed to the
repository's create() method.

generate_guidance() in THIS milestone does NOT call any AI/LLM provider —
per Step 9's explicit scope, it produces a placeholder recommendation so
the API surface is testable end-to-end. The real guidance_generation AI
touchpoint (architecture doc Section 7.1) replaces this placeholder logic
in a future milestone; nothing here should be mistaken for that.
"""
from beanie import PydanticObjectId

from app.core.exceptions import GuidanceGenerationError, GuidanceRecommendationNotFoundError
from app.models.career_guidance import GuidanceRecommendation, RecommendedPath
from app.repositories.career_guidance_repository import CareerGuidanceRepository


class CareerGuidanceService:
    """
    Orchestrates CareerGuidanceRepository. Holds no state beyond the
    repository it's constructed with — cheap to create per-request, same
    pattern as every prior service.
    """

    def __init__(self, guidance_repository: CareerGuidanceRepository):
        self._guidance_repo = guidance_repository

    async def get_recommendation(self, recommendation_id: str) -> GuidanceRecommendation:
        """
        Retrieves a single recommendation by id.

        NOTE: unlike get_attempt/get_item in prior services, this method
        signature (per Step 9's explicit spec) takes ONLY
        recommendation_id — no user_id parameter. That means ownership
        scoping is not enforced at this method's boundary the way it is
        elsewhere in this codebase. This matches what was explicitly
        requested; flagging it as a deliberate scope note rather than
        silently adding a user_id parameter you didn't ask for. If
        ownership enforcement is required here, it would need to be
        added in a follow-up step with your confirmation.

        Raises:
            GuidanceRecommendationNotFoundError: if no recommendation
                exists for this id.
        """
        recommendation = await self._guidance_repo.get_by_id(recommendation_id)
        if recommendation is None:
            raise GuidanceRecommendationNotFoundError("Guidance recommendation not found")
        return recommendation

    async def list_user_recommendations(
        self, user_id: PydanticObjectId
    ) -> list[GuidanceRecommendation]:
        """
        Lists all recommendations generated for a user, newest first.
        An empty result (a user with no recommendations yet) is a
        normal outcome, never an error.
        """
        return await self._guidance_repo.list_for_user(user_id)

    async def get_latest_recommendation(
        self, user_id: PydanticObjectId
    ) -> GuidanceRecommendation:
        """
        Retrieves the single newest recommendation for a user.

        Raises:
            GuidanceRecommendationNotFoundError: if the user has no
                recommendations at all.
        """
        recommendation = await self._guidance_repo.get_latest_for_user(user_id)
        if recommendation is None:
            raise GuidanceRecommendationNotFoundError(
                "No guidance recommendation exists for this user yet"
            )
        return recommendation

    async def generate_guidance(
        self,
        user_id: PydanticObjectId,
        assessment_id: str | None = None,
    ) -> GuidanceRecommendation:
        """
        Creates a new guidance recommendation for a user.

        PLACEHOLDER LOGIC, per Step 9's explicit scope: this method does
        NOT call any AI/LLM provider. It constructs a single
        placeholder RecommendedPath so the API is exercisable
        end-to-end, ahead of the real guidance_generation AI touchpoint
        (architecture doc Section 7.1) being implemented in a future
        milestone.

        If assessment_id is provided, it is converted to
        PydanticObjectId and stored as based_on_assessment_id — with NO
        validation that it refers to a real or owned AssessmentAttempt
        (see constructor scope note above: that would require
        CareerAssessmentRepository, not part of this step's
        constructor). A malformed assessment_id string would raise here
        during the PydanticObjectId conversion — that failure is
        treated as a generation failure (GuidanceGenerationError), since
        from this method's perspective it's an unexpected failure to
        produce a valid recommendation, not a missing-resource case.

        Raises:
            GuidanceGenerationError: if assessment_id is malformed, or
                if repository persistence fails unexpectedly.
        """
        try:
            based_on_assessment_id = (
                PydanticObjectId(assessment_id) if assessment_id is not None else None
            )

            placeholder_recommendation = GuidanceRecommendation(
                user_id=user_id,
                based_on_assessment_id=based_on_assessment_id,
                recommended_paths=[
                    RecommendedPath(
                        path_name="Software Engineering",
                        rationale=(
                            "Placeholder recommendation — AI-driven guidance "
                            "generation is not yet implemented. This path is "
                            "returned so the Career Guidance API can be "
                            "exercised end-to-end ahead of that integration."
                        ),
                        confidence=0.5,
                    )
                ],
            )

            return await self._guidance_repo.create(placeholder_recommendation)
        except GuidanceGenerationError:
            raise
        except Exception as exc:
            raise GuidanceGenerationError(
                "Failed to generate a guidance recommendation"
            ) from exc