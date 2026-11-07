"""AI knowledge base (RAG) persistence.

The knowledge base is a *role-aware* retrieval store: a document is not merely
text, it carries the scope that decides who may retrieve it. Four things are
modelled here, and the separation matters:

* :class:`KnowledgeDocument` -- the stable identity (category, owning company,
  sensitivity, language). Its retrievable text lives in versions, never here.
* :class:`KnowledgeVersion` -- an immutable revision with an approval status.
  Only an ``approved`` version is indexed, so an unreviewed draft can never
  reach an answer.
* :class:`KnowledgeChunk` -- a searchable slice of one approved version, with
  its own denormalised scope columns (company, sensitivity) so a retrieval
  query can filter by permission *in SQL* rather than fetching and then
  discarding. That is the structural defence against cross-company leakage.
* :class:`KnowledgeProposal` -- an owner-reviewed correction/learning proposal.
  It never edits a document by itself; approval is what applies it.

Retrieval ranking uses PostgreSQL full-text search when the backend supports it
(``to_tsvector``) and a portable lexical fallback otherwise (SQLite, which the
test suite uses). The fallback is a real search, not a stub: it matches
whole-word terms case-insensitively across the chunk text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import (
    KnowledgeDocumentStatus,
    KnowledgeProposalStatus,
    KnowledgeSensitivity,
)

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User


class KnowledgeCategory(Base, TimestampMixin):
    """A configurable knowledge grouping (Policy, Procedure, Guideline, ...)."""

    __tablename__ = "knowledge_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name_ar: Mapped[str] = mapped_column(String(160), nullable=False)
    name_en: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    documents: Mapped[list["KnowledgeDocument"]] = relationship(
        back_populates="category"
    )


class KnowledgeDocument(Base, TimestampMixin):
    """The stable identity of a knowledge item.

    ``company_id`` is NULL for holding-wide knowledge and set for knowledge that
    belongs to one subsidiary. ``sensitivity`` is the coarse ladder evaluated at
    retrieval time (see :class:`KnowledgeSensitivity`).
    """

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_knowledge_documents_slug"),
        # Composite scope index for the retrieval filter. The single-column
        # indexes come from ``index=True`` on the columns themselves; adding a
        # second Index on the same column would duplicate the name and break
        # ``create_all``.
        Index("ix_knowledge_documents_scope", "company_id", "sensitivity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_categories.id", ondelete="SET NULL"), nullable=True
    )
    # NULL == holding-wide knowledge; set == owned by one subsidiary.
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title_ar: Mapped[str] = mapped_column(String(240), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(240), nullable=True)
    summary_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    sensitivity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=KnowledgeSensitivity.HOLDING.value,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=KnowledgeDocumentStatus.DRAFT.value,
        index=True,
    )
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="ar")
    # The version currently indexed for retrieval. NULL until a version is
    # approved, which is why a draft is never retrievable.
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    category: Mapped["KnowledgeCategory | None"] = relationship(
        back_populates="documents"
    )
    company: Mapped["Company | None"] = relationship()
    versions: Mapped[list["KnowledgeVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeVersion.version_number",
        foreign_keys="KnowledgeVersion.document_id",
    )
    current_version: Mapped["KnowledgeVersion | None"] = relationship(
        foreign_keys="KnowledgeDocument.current_version_id", post_update=True
    )
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    proposals: Mapped[list["KnowledgeProposal"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class KnowledgeVersion(Base, TimestampMixin):
    """An immutable revision of a document.

    The body is the source text; chunks are derived from it when the version is
    approved. A new edit creates a new version rather than mutating an approved
    one, so the update history is complete and an approved answer is
    reproducible.
    """

    __tablename__ = "knowledge_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_knowledge_versions_doc_number"
        ),
        Index("ix_knowledge_versions_document", "document_id", "version_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    body_ar: Mapped[str] = mapped_column(Text, nullable=False)
    body_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=KnowledgeDocumentStatus.DRAFT.value,
        index=True,
    )
    # Free-text note recorded when a version is approved or archived, so the
    # history explains *why* rather than only *that*.
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    document: Mapped["KnowledgeDocument"] = relationship(
        back_populates="versions", foreign_keys=[document_id]
    )
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base, TimestampMixin):
    """A searchable slice of one approved version.

    The scope columns (``company_id``, ``sensitivity``) are denormalised from
    the parent document on purpose: a retrieval query filters on them directly,
    so an out-of-scope chunk is never even loaded. ``search_text`` is the
    normalised body used by both rankers: PostgreSQL builds a ``to_tsvector``
    over it at query time, and the portable fallback matches its tokens. Keeping
    the rank expression out of the schema means the tables are byte-identical on
    SQLite and PostgreSQL, so a migration never needs a dialect branch.
    """

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "version_id", "chunk_index", name="uq_knowledge_chunks_version_index"
        ),
        Index("ix_knowledge_chunks_document", "document_id"),
        Index("ix_knowledge_chunks_scope", "company_id", "sensitivity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Lower-cased content for lexical ranking. Kept as its own column so the
    # ranker never does a per-row Python scan.
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Denormalised scope, copied from the parent document at index time.
    company_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sensitivity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    document: Mapped["KnowledgeDocument"] = relationship(back_populates="chunks")
    version: Mapped["KnowledgeVersion"] = relationship(back_populates="chunks")


class KnowledgeProposal(Base, TimestampMixin):
    """An owner-reviewed correction or learning proposal.

    Raised by a curator (or generated from a flagged answer), it names the
    document and the proposed change but changes nothing until the owner
    approves it. Approval is recorded here and applied by the service, which is
    the only path that may alter a document because of a proposal.
    """

    __tablename__ = "knowledge_proposals"
    __table_args__ = (
        Index("ix_knowledge_proposals_document", "document_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="correction")
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    proposed_body: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=KnowledgeProposalStatus.PENDING.value,
        index=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    raised_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # The version created when the proposal was approved, when applicable.
    applied_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="SET NULL"), nullable=True
    )

    document: Mapped["KnowledgeDocument | None"] = relationship(
        back_populates="proposals"
    )
