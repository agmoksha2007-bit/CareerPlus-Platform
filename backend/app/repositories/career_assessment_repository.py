"""
PURPOSE
-------
Data access layer for the AssessmentAttempt aggregate. This is the ONLY
file (besides app/core/database.py, which just registers the model) that
queries app.models.career_assessment.AssessmentAttempt directly.

CareerAssessmentService (a later step) depends on THIS class, never on
Beanie or AssessmentAttempt directly — same pattern as every prior
repository in this codebase. Contains NO business logic: no computing
trait_scores, no AI interpretation, no recommending careers. Those are
entirely out of scope for this file.
"""
from beanie import PydanticObjectId

from app.models.career_assessment import AssessmentAttempt, AssessmentType


class CareerAssessmentRepository:
    """
    Every read/write method here is scoped by user_id at the QUERY
    level, not via a separate ownership check performed after fetching
    — same deliberate security property as CareerVaultRepository (M2)
    and the Milestone 3 repositories.
    """

    async def create(
        self,
        user_id: PydanticObjectId,
        assessment_type: AssessmentType,
    ) -> AssessmentAttempt:
        """
        Starts a new assessment attempt with no responses yet and no
        result — matching AssessmentAttempt's in-progress state as
        designed in Step 1. user_id is always supplied by the caller
        (the service layer, sourced from the authenticated user), never
        inferred here.
        """
        attempt = AssessmentAttempt(
            user_id=user_id,
            assessment_type=assessment_type,
        )
        await attempt.insert()
        return attempt

    async def get_by_id(
        self, attempt_id: str, user_id: PydanticObjectId
    ) -> AssessmentAttempt | None:
        """
        Fetches a single attempt by id, scoped to the given user_id in
        the SAME query. Returns None if the id is malformed, doesn't
        exist, or belongs to a different user — all three cases stay
        indistinguishable at this layer by design, same as every prior
        repository's get_by_id.
        """
        try:
            object_id = PydanticObjectId(attempt_id)
        except Exception:
            return None

        return await AssessmentAttempt.find_one(
            AssessmentAttempt.id == object_id,
            AssessmentAttempt.user_id == user_id,
        )

    async def list_by_user(self, user_id: PydanticObjectId) -> list[AssessmentAttempt]:
        """
        Returns all assessment attempts belonging to user_id — a user's
        complete attempt history, including retakes. Sorted by
        created_at descending (most recent first), same default
        ordering convention as CareerVaultRepository.list_by_user (M2).
        """
        return (
            await AssessmentAttempt.find(AssessmentAttempt.user_id == user_id)
            .sort(-AssessmentAttempt.created_at)
            .to_list()
        )

    async def update(
        self,
        attempt_id: str,
        user_id: PydanticObjectId,
        updates: dict,
    ) -> AssessmentAttempt | None:
        """
        Applies a partial update to an existing attempt, scoped to
        user_id. `updates` is a dict of {field_name: new_value} — only
        the keys present are changed. This is the single mechanism by
        which a future service will both record submitted responses
        (e.g. updates={"responses": [...]}) and store an AI-interpreted
        result (e.g. updates={"result": ..., "completed_at": ...}) —
        this repository has no opinion on which case it's handling.

        Unlike CareerVaultRepository.update (M2), this method does NOT
        unconditionally set a timestamp field: AssessmentAttempt (Step
        1) has no updated_at field, only created_at/completed_at, and
        completed_at is set explicitly by the caller including it in
        updates when appropriate — not implicitly by this method.

        Returns the updated attempt, or None if no matching attempt was
        found for this id + user_id combination.
        """
        attempt = await self.get_by_id(attempt_id, user_id)
        if attempt is None:
            return None

        for field_name, value in updates.items():
            setattr(attempt, field_name, value)

        await attempt.save()
        return attempt

    async def delete(self, attempt_id: str, user_id: PydanticObjectId) -> bool:
        """
        Deletes an attempt scoped to user_id. Returns True if a matching
        attempt was found and deleted, False otherwise — the caller (a
        future service) decides what False should mean to an API
        consumer, not this method.
        """
        attempt = await self.get_by_id(attempt_id, user_id)
        if attempt is None:
            return False

        await attempt.delete()
        return True