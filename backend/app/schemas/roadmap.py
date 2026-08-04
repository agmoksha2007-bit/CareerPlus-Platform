"""
PURPOSE
-------
API request/response contracts for Roadmaps (Milestone 5, architecture doc
Section 4.2). This file contains ONLY Pydantic schemas — no database
queries, no enrollment logic, no milestone-completion logic. How a user
enrolls in a roadmap, and how milestone_status transitions between states,
are entirely service-layer concerns (app/services/roadmap_service.py, a
later step), never this file's.

Kept completely separate from app.models.roadmap: the Beanie Documents
there represent MongoDB storage; these schemas represent the HTTP API
contract. The one exception is MilestoneCompletionStatus, a plain Python
Enum (not a Beanie Document) reused directly from the model — same
precedent as every prior schema file in this codebase (e.g. VaultItemType
in career_vault schemas, AssessmentType in career_assessment schemas).
Every id in these schemas is a plain string, converted at the
service-layer boundary.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.roadmap import MilestoneCompletionStatus

# ======================================================================
# Template schemas
# ======================================================================


class RoadmapMilestoneResponse(BaseModel):
    """
    Response shape for one milestone within a roadmap template's
    milestones list. Mirrors app.models.roadmap.RoadmapMilestone's
    fields exactly, kept as a separate schema rather than reusing the
    model directly — same model/schema split used throughout this
    codebase.
    """

    order: int
    title: str
    description: str
    linked_module: str | None
    linked_resource_id: str | None

    model_config = ConfigDict(from_attributes=True)


class RoadmapTemplateResponse(BaseModel):
    """
    Response shape for a single roadmap template — returned by
    create/get/list endpoints alike, same one-schema-per-resource
    pattern as every prior *Response schema in this codebase.
    """

    id: str
    title: str
    description: str
    milestones: list[RoadmapMilestoneResponse]

    model_config = ConfigDict(from_attributes=True)


class RoadmapTemplateListResponse(BaseModel):
    """
    Response shape for the list-templates endpoint (a later step).
    Wraps the template list in a named field, same wrapped-list
    convention as GuidanceRecommendationListResponse (Step 6).
    """

    roadmaps: list[RoadmapTemplateResponse]


# ======================================================================
# User progress schemas
# ======================================================================


class MilestoneStatusResponse(BaseModel):
    """
    Response shape for one milestone's progress status, embedded inside
    UserRoadmapProgressResponse.milestone_status. Mirrors
    app.models.roadmap.MilestoneStatus's fields exactly.

    `status` reuses MilestoneCompletionStatus directly from the model
    (see module docstring) rather than redefining an equivalent enum.
    """

    milestone_order: int
    status: MilestoneCompletionStatus
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class UserRoadmapProgressResponse(BaseModel):
    """
    Response shape for a single user's progress against a single
    template — returned by enroll/get/list endpoints alike.
    """

    id: str
    user_id: str
    roadmap_template_id: str
    milestone_status: list[MilestoneStatusResponse]

    model_config = ConfigDict(from_attributes=True)


class UserRoadmapProgressListResponse(BaseModel):
    """
    Response shape for the list-progress endpoint (a later step).
    Wraps the progress list in a named field, same wrapped-list
    convention used throughout this schema file and this codebase.
    """

    progress: list[UserRoadmapProgressResponse]


class RoadmapEnrollmentRequest(BaseModel):
    """
    Request body for enrolling in a roadmap template. No custom
    validators: verifying that roadmap_template_id actually refers to a
    real template is a business rule (requires a database lookup) —
    that check belongs to the service layer, a later step, not this
    schema.
    """

    roadmap_template_id: str = Field(min_length=1)