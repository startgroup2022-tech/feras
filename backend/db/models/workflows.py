"""Configurable workflows and the approval runtime.

Like forms, workflows are versioned so that editing a definition never rewrites
the history of a request already in flight:

* :class:`WorkflowDefinition` is the stable identity (code, names, linked form).
* :class:`WorkflowVersion` is a snapshot of the step chain. A draft may be
  edited; a published version is frozen.
* :class:`WorkflowStep` hangs off a version and carries an *explicit* assignee
  rule (``AssignmentType``) -- never a script.

The runtime:

* :class:`WorkflowInstance` is created from a *published version* and pins
  ``workflow_version_id`` plus ``current_step_id``.
* :class:`ApprovalTask` is one pending action for one resolved approver.
* :class:`ApprovalEvent` is the immutable timeline; nothing here is ever
  deleted or updated.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import (
    FormScope,
    TaskStatus,
    WorkflowStatus,
)

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User


class WorkflowDefinition(Base, TimestampMixin):
    __tablename__ = "workflow_definitions"
    __table_args__ = (
        Index("ix_workflow_definitions_form_status", "form_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    description_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The form this workflow approves. A form may have several (draft) workflow
    # candidates; the published one is what the engine selects.
    form_id: Mapped[int] = mapped_column(
        ForeignKey("dynamic_forms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FormScope.COMPANY.value
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=WorkflowStatus.DRAFT.value, index=True
    )
    # When true, a submission may proceed into the workflow even if mandatory
    # requirements are unmet, provided the actor holds ``approval.override``.
    allow_requirement_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list["WorkflowVersion"]] = relationship(
        back_populates="definition",
        cascade="all, delete-orphan",
        order_by="WorkflowVersion.version_number",
    )

    @property
    def published_version(self) -> "WorkflowVersion | None":
        for version in self.versions:
            if version.status == WorkflowStatus.PUBLISHED.value:
                return version
        return None

    @property
    def latest_version(self) -> "WorkflowVersion | None":
        if not self.versions:
            return None
        return max(self.versions, key=lambda v: v.version_number)


class WorkflowVersion(Base, TimestampMixin):
    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint(
            "definition_id", "version_number", name="uq_workflow_versions_number"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=WorkflowStatus.DRAFT.value, index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    definition: Mapped[WorkflowDefinition] = relationship(back_populates="versions")
    steps: Mapped[list["WorkflowStep"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.display_order",
    )


class WorkflowStep(Base, TimestampMixin):
    """One step of an approval chain with an explicit assignment rule."""

    __tablename__ = "workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_version_id", "key", name="uq_workflow_steps_key"),
        Index("ix_workflow_steps_version_order", "workflow_version_id", "display_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_version_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assignment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Declarative payload for the assignment rule:
    #   user -> {"user_id": N}
    #   role -> {"role_code": "finance_manager"}
    #   department_manager -> {"department_id": N} (optional)
    #   company_manager -> {}
    #   submitter_manager -> {} (submitter's department manager)
    assignment_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    required_permission: Mapped[str | None] = mapped_column(String(80), nullable=True)
    allow_approve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_reject: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_return: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    require_comment_on_reject: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    sla_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    version: Mapped[WorkflowVersion] = relationship(back_populates="steps")


class WorkflowInstance(Base, TimestampMixin):
    """A running approval for one submission.

    ``workflow_version_id`` pins the exact step chain; later edits to the
    definition create a new version and never touch this instance.
    """

    __tablename__ = "workflow_instances"
    __table_args__ = (
        Index("ix_workflow_instances_submission", "submission_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("form_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    workflow_definition_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    workflow_version_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="RESTRICT"), nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="in_review", index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tasks: Mapped[list["ApprovalTask"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan"
    )
    events: Mapped[list["ApprovalEvent"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="ApprovalEvent.id",
    )


class ApprovalTask(Base, TimestampMixin):
    """A pending (or resolved) approval action for one resolved approver."""

    __tablename__ = "approval_tasks"
    __table_args__ = (
        Index("ix_approval_tasks_assignee_status", "assignee_id", "status"),
        Index("ix_approval_tasks_instance_status", "instance_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_steps.id", ondelete="RESTRICT"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TaskStatus.PENDING.value, index=True
    )
    acted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    instance: Mapped[WorkflowInstance] = relationship(back_populates="tasks")


class ApprovalEvent(Base, TimestampMixin):
    """The immutable approval timeline. Rows are only ever inserted."""

    __tablename__ = "approval_events"
    __table_args__ = (
        Index("ix_approval_events_instance", "instance_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("form_submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("approval_tasks.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)

    instance: Mapped[WorkflowInstance] = relationship(back_populates="events")


__all__ = [
    "WorkflowDefinition",
    "WorkflowVersion",
    "WorkflowStep",
    "WorkflowInstance",
    "ApprovalTask",
    "ApprovalEvent",
]
