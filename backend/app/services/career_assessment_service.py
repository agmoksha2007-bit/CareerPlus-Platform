"""
PURPOSE
-------
Business logic for Career Assessment: creating attempts, recording and
correcting responses, retrieving and listing attempts, and deleting
attempts. This layer depends ONLY on CareerAssessmentRepository — it never
imports Beanie or app.models.career_assessment.AssessmentAttempt directly.

Explicitly OUT OF SCOPE for this file, per Milestone 4 Step 5: no AI
interpretation, no trait-score calculation, no career recommendations, no
LLM integration. An attempt's `result` field is only ever set here as
whatever value a caller (a future step) provides — this service does not
compute it.
"""
from beanie import PydanticObjectId

from app.core.exceptions import AssessmentAlreadyCompletedError, AssessmentAttemptNotFoundError
from app.models.career_assessment import AssessmentResponseItem
from app.repositories.career_assessment_repository import CareerAssessmentRepository
from app.schemas.career_assessment import (
    AssessmentAttemptListResponse,
    AssessmentAttemptPublic,
    AssessmentResponseItemInput,
    AssessmentResponseItemPublic,
    AssessmentResultPublic,
)


class CareerAssessmentService:
    """
    Orchestrates CareerAssessmentRepository to implement the six Career
    Assessment operations. Holds no state beyond the repository it's
    constructed with — cheap to create per-request, same pattern as
    every prior service.
    """

    def __init__(self, assessment_repository: CareerAssessmentRepository):
        self._assessment_repo = assessment_repository

    async def create_attempt(
        self, user_id: PydanticObjectId, assessment_type
    ) -> AssessmentAttemptPublic:
        """
        Starts a new, empty assessment attempt for the given user. No
        validation beyond what the schema layer (Step 4) already
        performed on assessment_type — this method is pure
        orchestration: hand the field to the repository, map the result
        to the public response shape.
        """
        attempt = await self._assessment_repo.create(user_id, assessment_type)
        return self._to_public(attempt)

    async def get_attempt(
        self, attempt_id: str, user_id: PydanticObjectId
    ) -> AssessmentAttemptPublic:
        """
        Retrieves a single attempt by id, scoped to the requesting user.

        Raises:
            AssessmentAttemptNotFoundError: if no matching attempt
                exists for this id + user_id combination.
        """
        attempt = await self._assessment_repo.get_by_id(attempt_id, user_id)
        if attempt is None:
            raise AssessmentAttemptNotFoundError("Assessment attempt not found")
        return self._to_public(attempt)

    async def list_attempts(self, user_id: PydanticObjectId) -> AssessmentAttemptListResponse:
        """
        Lists all assessment attempts belonging to the given user — the
        user's complete attempt history, including retakes. An empty
        result (a user with no attempts yet) is a normal outcome, never
        an error.
        """
        attempts = await self._assessment_repo.list_by_user(user_id)
        return AssessmentAttemptListResponse(
            attempts=[self._to_public(attempt) for attempt in attempts],
            total=len(attempts),
        )

    async def submit_responses(
        self,
        attempt_id: str,
        user_id: PydanticObjectId,
        responses: list[AssessmentResponseItemInput],
    ) -> AssessmentAttemptPublic:
        """
        Records a batch of responses against an existing, in-progress
        attempt — a full replacement of the attempt's responses list
        (per Step 4's schema design; no per-item merging happens here).

        Business rule enforced here: an attempt that already has a
        result (i.e. is completed) cannot have its responses submitted
        again — see the AssessmentAlreadyCompletedError explanation
        above for why this check exists.

        Raises:
            AssessmentAttemptNotFoundError: if no matching attempt
                exists for this id + user_id combination.
            AssessmentAlreadyCompletedError: if the attempt already has
                a result.
        """
        attempt = await self._assessment_repo.get_by_id(attempt_id, user_id)
        if attempt is None:
            raise AssessmentAttemptNotFoundError("Assessment attempt not found")

        if attempt.result is not None:
            raise AssessmentAlreadyCompletedError(
                "Cannot submit responses for an assessment attempt that is already completed"
            )

        updated_attempt = await self._assessment_repo.update(
            attempt_id,
            user_id,
            {"responses": self._to_model_responses(responses)},
        )
        return self._to_public(updated_attempt)

    async def update_responses(
        self,
        attempt_id: str,
        user_id: PydanticObjectId,
        responses: list[AssessmentResponseItemInput],
    ) -> AssessmentAttemptPublic:
        """
        Corrects previously-recorded responses on an attempt that has
        not yet been completed — same full-replacement semantics and
        same completion guard as submit_responses above. Kept as a
        separate method (rather than reusing submit_responses
        internally) because the two represent distinct client intents
        (first recording vs. correction) even though their current
        implementation is identical — matching Step 4's own reasoning
        for keeping their request schemas separate.

        Raises:
            AssessmentAttemptNotFoundError: if no matching attempt
                exists for this id + user_id combination.
            AssessmentAlreadyCompletedError: if the attempt already has
                a result.
        """
        attempt = await self._assessment_repo.get_by_id(attempt_id, user_id)
        if attempt is None:
            raise AssessmentAttemptNotFoundError("Assessment attempt not found")

        if attempt.result is not None:
            raise AssessmentAlreadyCompletedError(
                "Cannot update responses for an assessment attempt that is already completed"
            )

        updated_attempt = await self._assessment_repo.update(
            attempt_id,
            user_id,
            {"responses": self._to_model_responses(responses)},
        )
        return self._to_public(updated_attempt)

    async def delete_attempt(self, attempt_id: str, user_id: PydanticObjectId) -> None:
        """
        Deletes an assessment attempt, scoped to the requesting user.

        Raises:
            AssessmentAttemptNotFoundError: if no matching attempt
                exists for this id + user_id combination.
        """
        deleted = await self._assessment_repo.delete(attempt_id, user_id)
        if not deleted:
            raise AssessmentAttemptNotFoundError("Assessment attempt not found")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_model_responses(
        responses: list[AssessmentResponseItemInput],
    ) -> list[AssessmentResponseItem]:
        """
        Converts validated request-schema response items into the
        model's embedded AssessmentResponseItem shape, ready to hand to
        the repository. The repository's update() stores whatever it's
        given as-is (Step 3) — this conversion is what bridges "a
        validated request" to "a model-shaped value," which is a
        service-layer responsibility, not the repository's.
        """
        return [
            AssessmentResponseItem(question_id=item.question_id, response=item.response)
            for item in responses
        ]

    @staticmethod
    def _to_public(attempt) -> AssessmentAttemptPublic:
        """The one place an AssessmentAttempt becomes an API-facing AssessmentAttemptPublic."""
        return AssessmentAttemptPublic(
            id=str(attempt.id),
            assessment_type=attempt.assessment_type,
            responses=[
                AssessmentResponseItemPublic(
                    question_id=item.question_id, response=item.response
                )
                for item in attempt.responses
            ],
            result=(
                AssessmentResultPublic(
                    trait_scores=attempt.result.trait_scores,
                    recommended_domains=attempt.result.recommended_domains,
                    summary=attempt.result.summary,
                )
                if attempt.result is not None
                else None
            ),
            created_at=attempt.created_at,
            completed_at=attempt.completed_at,
        )