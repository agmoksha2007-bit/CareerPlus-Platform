"""
PURPOSE
-------
Beanie document schemas for the Roadmaps sub-module of Milestone 5
(architecture doc Section 4.2, Group B: Direction). Two top-level
collections live in this one file, per the doc's own folder-structure
comment:

  - RoadmapTemplate      -> "roadmap_templates"      (platform-curated)
  - UserRoadmapProgress  -> "user_roadmap_progress"   (per-user)

RoadmapMilestone and MilestoneStatus are NOT Beanie Documents — they are
embedded Pydantic models, following the same embedding convention used in
every prior milestone's models (e.g. SkillSignalSource embedded in
UserSkillProfile, Milestone 3).

This file contains NO business logic: enrollment rules, milestone
completion rules, and progress computation are service-layer concerns
(a later step), not this model's job.
"""
from datetime import datetime, timezone
from enum import Enum

from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field


class RoadmapMilestone(BaseModel):
    """
    Embedded record of one milestone within a RoadmapTemplate. Field
    names match architecture doc Section 4.2's own description exactly:
    {order, title, description, linked_module, linked_resource_id}.

    Not a Beanie Document — always read/written as part of its parent
    RoadmapTemplate.milestones list.
    """

    order: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)

    # Plain string, not an enum: per architecture doc Section 4.2, this
    # "optionally points at Aptitude/Programming Practice or a specific
    # roadmap step's practice set" — modules that do not exist yet
    # (Milestone 7). Same reasoning as SkillSignalSource.module
    # (Milestone 3): hardcoding an enum now would require editing this
    # file every time a linkable module ships.
    linked_module: str | None = None

    # Plain string, not PydanticObjectId: could reference a record in
    # any future collection, each with its own id space — same
    # reasoning as SkillSignalSource.reference_id (Milestone 3).
    linked_resource_id: str | None = None


class RoadmapTemplate(Document):
    """
    A single platform-curated roadmap (e.g. "Become a Backend
    Engineer"). No user_id field — this is admin-maintained content, not
    user-generated, same pattern as SkillTaxonomyEntry (Milestone 3).
    """

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    milestones: list[RoadmapMilestone] = Field(default_factory=list)

    class Settings:
        name = "roadmap_templates"


class MilestoneCompletionStatus(str, Enum):
    """
    The fixed set of per-milestone progress states named in
    architecture doc Section 4.2. A str Enum, not free text — same
    reasoning as every prior fixed-vocabulary field in this codebase
    (VaultItemType, AssessmentType, SkillCategory).
    """
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


class MilestoneStatus(BaseModel):
    """
    Embedded record of a user's progress against ONE milestone within a
    roadmap. References the milestone by its `order` position within
    the template — NOT by duplicating the milestone's title/description
    — so a progress record never goes stale if a template's milestone
    text is later edited (see design notes above).

    Not a Beanie Document — always read/written as part of its parent
    UserRoadmapProgress.milestone_status list.
    """

    milestone_order: int = Field(ge=0)
    status: MilestoneCompletionStatus = MilestoneCompletionStatus.NOT_STARTED
    completed_at: datetime | None = None


class UserRoadmapProgress(Document):
    """
    A single user's progress against a single RoadmapTemplate.

    ASSUMPTION FLAGGED (see design notes above): architecture doc
    Section 4.2 does not explicitly state whether a user may have more
    than one progress record against the same template (e.g.
    restarting). The compound index below is deliberately NOT unique —
    easy to make unique later if "one record per user per template,
    ever" is the intended rule.
    """

    user_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]
    roadmap_template_id: Indexed(PydanticObjectId)  # type: ignore[valid-type]

    milestone_status: list[MilestoneStatus] = Field(default_factory=list)

    class Settings:
        name = "user_roadmap_progress"