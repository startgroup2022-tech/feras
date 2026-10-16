"""AI conversation and audit log models.

The AI tables record the *conversation* only. The data an assistant is allowed
to reason over is never stored here -- it is assembled at request time from the
database, after company isolation has been enforced. This is what prevents an
assistant from being fed another company's figures.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import AIMessageRole

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User


class AIConversation(Base, TimestampMixin):
    """A conversation thread, either holding-wide or scoped to one company."""

    __tablename__ = "ai_conversations"
    __table_args__ = (
        Index("ix_ai_conversations_scope_company", "scope", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # NULL for holding-wide conversations; set (and required) for company scope.
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    company: Mapped["Company | None"] = relationship(back_populates="ai_conversations")
    user: Mapped["User"] = relationship()
    messages: Mapped[list["AIMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AIMessage.id",
    )


class AIMessage(Base, TimestampMixin):
    __tablename__ = "ai_messages"
    __table_args__ = (
        Index("ix_ai_messages_conversation", "conversation_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AIMessageRole.USER.value
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Provenance for grounded answers: which company ids backed this message.
    context_company_ids: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    conversation: Mapped[AIConversation] = relationship(back_populates="messages")


class AuditLog(Base):
    """Append-only record of security-relevant and business-critical actions.

    Intentionally has no ``updated_at``: audit rows are immutable.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor_time", "actor_user_id", "created_at"),
        Index("ix_audit_logs_company", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # JSON-encoded, already-redacted metadata. Named ``meta_json`` to avoid
    # clashing with SQLAlchemy's reserved ``metadata`` attribute.
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
