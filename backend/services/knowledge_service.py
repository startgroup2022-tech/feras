"""Knowledge base service: scoped curation and retrieval (RAG).

Two rules shape everything here:

1. **Scope before scoring.** The caller's permitted companies, the sensitivity
   ladder and the approved-version filter are applied as SQL ``WHERE`` clauses
   *before* any text is ranked. An out-of-scope chunk is never loaded, so it can
   never contribute to an answer -- the same structural defence the rest of the
   platform uses for company data.
2. **Only approved knowledge is retrievable.** Chunks are produced when a
   version is approved and are deleted when it is superseded or archived, so a
   draft or a rejected revision is invisible to retrieval by construction.

Ranking is PostgreSQL full-text search when available and a portable lexical
score otherwise (SQLite, used by the test suite). Both rank the same
``search_text`` column, so behaviour is consistent across backends.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import (
    KnowledgeChunkSource,
    KnowledgeDocumentStatus,
    KnowledgeProposalStatus,
    KnowledgeSensitivity,
)
from backend.db.models.identity import Company, User
from backend.db.models.knowledge import (
    KnowledgeCategory,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeProposal,
    KnowledgeVersion,
)
from backend.rbac.authorization import (
    accessible_company_ids,
    has_permission,
    is_holding_wide,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.services import audit_service
from backend.services.confidential_access_service import is_confidential_owner

# Arabic diacritics (tashkeel) and tatweel, removed before tokenising so a
# question matches a document regardless of vocalisation.
_ARABIC_MARKS = re.compile(r"[\u0617-\u061A\u064B-\u065F\u0670\u0640]")
_TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)


def normalize_arabic(text: str) -> str:
    """Fold Arabic orthographic variants so search is spelling-tolerant."""
    text = unicodedata.normalize("NFKC", text or "")
    text = _ARABIC_MARKS.sub("", text)
    text = (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
    return text


def tokenize(text: str) -> list[str]:
    """Lower-cased, normalised word tokens."""
    return [t.lower() for t in _TOKEN_RE.findall(normalize_arabic(text))]


def _fts_query(tokens) -> str:
    """A PostgreSQL ``to_tsquery`` string that matches on *any* term.

    Terms are OR-ed so the PostgreSQL path agrees with the portable lexical
    fallback (which scores any shared token). ``plainto_tsquery`` would AND the
    terms instead, silently making multi-word queries stricter on production
    PostgreSQL than on SQLite.
    """
    return " | ".join(sorted(t for t in tokens if t))


# --------------------------------------------------------------------------
# chunking
# --------------------------------------------------------------------------
def chunk_text(body: str, *, size: int, overlap: int) -> list[str]:
    """Split ``body`` into overlapping windows on paragraph/sentence boundaries.

    Windows prefer to break at a newline, then a sentence end, then a space, so
    a chunk usually reads as whole sentences. Overlap keeps a sentence that
    straddles a boundary retrievable from either side.
    """
    body = (body or "").strip()
    if not body:
        return []
    size = max(200, size)
    overlap = max(0, min(overlap, size // 2))
    chunks: list[str] = []
    start = 0
    length = len(body)
    while start < length:
        end = min(start + size, length)
        if end < length:
            window = body[start:end]
            cut = max(window.rfind("\n"), window.rfind(". "), window.rfind("؟ "), window.rfind("! "))
            if cut >= size // 2:
                end = start + cut + 1
        chunk = body[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


# --------------------------------------------------------------------------
# retrieval
# --------------------------------------------------------------------------
@dataclass(slots=True)
class RetrievedChunk:
    """A scored chunk plus the citation data the API exposes."""

    chunk_id: int
    document_id: int
    version_id: int
    title_ar: str
    title_en: str | None
    company_id: int | None
    sensitivity: str
    content: str
    score: float
    source: str

    def citation(self) -> dict:
        return {
            "document_id": self.document_id,
            "version_id": self.version_id,
            "title_ar": self.title_ar,
            "title_en": self.title_en,
            "company_id": self.company_id,
            "sensitivity": self.sensitivity,
            "chunk_id": self.chunk_id,
            "score": round(self.score, 4),
            "source": self.source,
            "excerpt": self.content[:280],
        }


def _permitted_sensitivities(user: User) -> list[str]:
    """The sensitivity levels this user may retrieve, from least to most open.

    ``CONFIDENTIAL`` requires ownership (or a delegated grant); ``HOLDING``
    requires a holding-wide role; ``COMPANY`` is further narrowed by the company
    filter in the query; ``PUBLIC`` is available to any authenticated user.
    """
    levels = [KnowledgeSensitivity.PUBLIC.value]
    if is_holding_wide(user):
        levels.append(KnowledgeSensitivity.HOLDING.value)
    if is_confidential_owner(user):
        levels.append(KnowledgeSensitivity.CONFIDENTIAL.value)
    # COMPANY documents are still gated by the company filter below; listing the
    # level here only lets the query reach them, never bypasses the scope.
    levels.append(KnowledgeSensitivity.COMPANY.value)
    return levels


def _scope_filter(stmt, user: User):
    """Apply the sensitivity ladder and company scope to a chunk query.

    Each permitted level contributes one OR clause, so a confidential
    holding-wide document is not accidentally filtered out by a company test.
    ``COMPANY`` knowledge is the only level that consults the company scope; a
    holding-wide user (``allowed is None``) may read any company's knowledge,
    while a company-scoped user is confined to their grants (and, with no
    grants, sees nothing at this level).
    """
    allowed = accessible_company_ids(user)
    clauses = [KnowledgeChunk.sensitivity == KnowledgeSensitivity.PUBLIC.value]

    if is_holding_wide(user):
        clauses.append(KnowledgeChunk.sensitivity == KnowledgeSensitivity.HOLDING.value)
    if is_confidential_owner(user):
        clauses.append(KnowledgeChunk.sensitivity == KnowledgeSensitivity.CONFIDENTIAL.value)

    company_level = KnowledgeChunk.sensitivity == KnowledgeSensitivity.COMPANY.value
    if allowed is None:
        clauses.append(company_level)
    elif allowed:
        clauses.append(company_level & KnowledgeChunk.company_id.in_(allowed))
    # With no company grants the caller keeps only the PUBLIC clause above.

    return stmt.where(or_(*clauses))


def _lexical_score(query_tokens: set[str], chunk_tokens: list[str]) -> float:
    """Overlap score: matched query terms weighted by their rarity in the chunk."""
    if not query_tokens or not chunk_tokens:
        return 0.0
    counts: dict[str, int] = {}
    for token in chunk_tokens:
        if token in query_tokens:
            counts[token] = counts.get(token, 0) + 1
    if not counts:
        return 0.0
    # A term that appears at all counts once; repeated mentions add a small
    # bonus, capped so a keyword-stuffed chunk cannot dominate.
    score = 0.0
    for token in counts:
        score += 1.0 + min(counts[token] - 1, 3) * 0.25
    return score / len(query_tokens)


def retrieve(
    db: Session,
    user: User,
    *,
    query: str,
    top_k: int | None = None,
    company_id: int | None = None,
) -> list[RetrievedChunk]:
    """Return the best approved chunks the caller may see for ``query``.

    ``company_id`` narrows retrieval to one company's knowledge (still subject
    to the caller's scope); it never widens access.
    """
    require_permission(user, Perm.AI_KNOWLEDGE_ASK)
    top_k = top_k or settings.AI_KNOWLEDGE_TOP_K
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return []

    stmt = (
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeDocument.status == KnowledgeDocumentStatus.APPROVED.value)
        .where(KnowledgeDocument.current_version_id == KnowledgeChunk.version_id)
    )
    stmt = _scope_filter(stmt, user)
    if company_id is not None:
        stmt = stmt.where(
            or_(KnowledgeChunk.company_id == company_id, KnowledgeChunk.company_id.is_(None))
        )

    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"
    results: list[RetrievedChunk] = []

    if dialect == "postgresql":
        # Match on *any* query term, not all of them. ``plainto_tsquery`` ANDs
        # its terms, which would make a multi-word Arabic query (e.g.
        # "اعتماد المشتريات") miss a chunk that contains only "المشتريات",
        # diverging from the lexical fallback below and from the documented
        # "consistent across backends" contract. Joining the terms with ``|``
        # gives the same any-term semantics on both backends.
        tsquery = func.to_tsquery("simple", _fts_query(query_tokens))
        tsv = func.to_tsvector("simple", KnowledgeChunk.search_text)
        rank = func.ts_rank(tsv, tsquery)
        stmt = (
            stmt.add_columns(rank.label("rank"))
            .where(tsv.op("@@")(tsquery))
            .order_by(rank.desc())
            .limit(top_k * 3)
        )
        for chunk, document, score in db.execute(stmt).all():
            results.append(
                _to_retrieved(chunk, document, float(score), KnowledgeChunkSource.FULLTEXT.value)
            )
    else:
        # Portable lexical fallback: fetch scope-filtered candidates and rank in
        # Python. The scope filter has already run in SQL, so this only ever
        # scores rows the caller may see.
        for chunk, document in db.execute(stmt).all():
            score = _lexical_score(query_tokens, tokenize(chunk.content))
            if score > 0:
                results.append(
                    _to_retrieved(chunk, document, score, KnowledgeChunkSource.LEXICAL.value)
                )
        results.sort(key=lambda r: r.score, reverse=True)

    # A document's title match is a strong signal; fold it into the score so a
    # titled "سياسة الصرف" ranks above a body mention.
    for item in results:
        title_tokens = set(tokenize((item.title_ar or "") + " " + (item.title_en or "")))
        if title_tokens & query_tokens:
            item.score += 1.5
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]


def _to_retrieved(
    chunk: KnowledgeChunk, document: KnowledgeDocument, score: float, source: str
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        document_id=document.id,
        version_id=chunk.version_id,
        title_ar=document.title_ar,
        title_en=document.title_en,
        company_id=chunk.company_id,
        sensitivity=chunk.sensitivity,
        content=chunk.content,
        score=score,
        source=source,
    )


# --------------------------------------------------------------------------
# curation: categories
# --------------------------------------------------------------------------
def list_categories(db: Session, user: User, *, include_inactive: bool = False):
    require_permission(user, Perm.AI_KNOWLEDGE_READ)
    stmt = select(KnowledgeCategory).order_by(
        KnowledgeCategory.display_order, KnowledgeCategory.id
    )
    if not include_inactive:
        stmt = stmt.where(KnowledgeCategory.is_active.is_(True))
    return list(db.execute(stmt).scalars())


def create_category(
    db: Session, user: User, *, code: str, name_ar: str, name_en: str,
    description: str | None = None, display_order: int = 0,
) -> KnowledgeCategory:
    require_permission(user, Perm.AI_KNOWLEDGE_MANAGE)
    if db.execute(
        select(KnowledgeCategory).where(KnowledgeCategory.code == code)
    ).scalar_one_or_none():
        raise ConflictError("A category with this code already exists.")
    category = KnowledgeCategory(
        code=code, name_ar=name_ar, name_en=name_en,
        description=description, display_order=display_order,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


# --------------------------------------------------------------------------
# curation: documents and versions
# --------------------------------------------------------------------------
def _require_company_scope(user: User, company_id: int | None) -> None:
    """A company-scoped curator may only manage knowledge for their companies."""
    if company_id is None:
        # Holding-wide knowledge is a holding privilege.
        if not is_holding_wide(user):
            raise ValidationError("Holding-wide knowledge requires holding access.")
        return
    allowed = accessible_company_ids(user)
    if allowed is not None and company_id not in allowed:
        raise NotFoundError("Company not found.")


def create_document(
    db: Session,
    user: User,
    *,
    slug: str,
    title_ar: str,
    title_en: str | None,
    body_ar: str,
    body_en: str | None = None,
    category_id: int | None = None,
    company_id: int | None = None,
    sensitivity: str = KnowledgeSensitivity.HOLDING.value,
    summary_ar: str | None = None,
    summary_en: str | None = None,
    source_reference: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> KnowledgeDocument:
    """Create a document with its first draft version (not yet retrievable)."""
    require_permission(user, Perm.AI_KNOWLEDGE_WRITE)
    _require_company_scope(user, company_id)
    if sensitivity not in {s.value for s in KnowledgeSensitivity}:
        raise ValidationError("Unknown sensitivity level.")
    if not body_ar or not body_ar.strip():
        raise ValidationError("The Arabic body is required.")
    if db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.slug == slug)
    ).scalar_one_or_none():
        raise ConflictError("A document with this slug already exists.")

    document = KnowledgeDocument(
        slug=slug,
        title_ar=title_ar,
        title_en=title_en,
        summary_ar=summary_ar,
        summary_en=summary_en,
        category_id=category_id,
        company_id=company_id,
        sensitivity=sensitivity,
        status=KnowledgeDocumentStatus.DRAFT.value,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(document)
    db.flush()
    version = KnowledgeVersion(
        document_id=document.id,
        version_number=1,
        body_ar=body_ar,
        body_en=body_en,
        status=KnowledgeDocumentStatus.DRAFT.value,
        source_reference=source_reference,
        created_by_id=user.id,
    )
    db.add(version)
    db.commit()
    db.refresh(document)
    audit_service.record(
        db,
        action=AuditAction.AI_KNOWLEDGE_DOCUMENT_CREATED,
        actor_user_id=user.id,
        entity_type="knowledge_document",
        entity_id=document.id,
        company_id=company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"slug": slug, "sensitivity": sensitivity},
    )
    return document


def add_version(
    db: Session,
    user: User,
    *,
    document_id: int,
    body_ar: str,
    body_en: str | None = None,
    source_reference: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> KnowledgeVersion:
    """Add a new draft version to a document (the previous one stays intact)."""
    require_permission(user, Perm.AI_KNOWLEDGE_WRITE)
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    _require_company_scope(user, document.company_id)
    if not body_ar or not body_ar.strip():
        raise ValidationError("The Arabic body is required.")

    last = db.execute(
        select(func.max(KnowledgeVersion.version_number)).where(
            KnowledgeVersion.document_id == document_id
        )
    ).scalar_one()
    version = KnowledgeVersion(
        document_id=document_id,
        version_number=int(last or 0) + 1,
        body_ar=body_ar,
        body_en=body_en,
        status=KnowledgeDocumentStatus.DRAFT.value,
        source_reference=source_reference,
        created_by_id=user.id,
    )
    db.add(version)
    document.updated_by_id = user.id
    db.commit()
    db.refresh(version)
    audit_service.record(
        db,
        action=AuditAction.AI_KNOWLEDGE_VERSION_ADDED,
        actor_user_id=user.id,
        entity_type="knowledge_document",
        entity_id=document_id,
        company_id=document.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"version": version.version_number},
    )
    return version


def approve_version(
    db: Session,
    user: User,
    *,
    version_id: int,
    review_note: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> KnowledgeVersion:
    """Approve a version and (re)index it, making it retrievable.

    Approving supersedes the document's previous chunks: they are deleted and
    replaced, so retrieval only ever sees the currently approved text.
    """
    require_permission(user, Perm.AI_KNOWLEDGE_APPROVE)
    version = db.get(KnowledgeVersion, version_id)
    if version is None:
        raise NotFoundError("Version not found.")
    document = db.get(KnowledgeDocument, version.document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    _require_company_scope(user, document.company_id)
    if version.status == KnowledgeDocumentStatus.APPROVED.value:
        raise ConflictError("This version is already approved.")

    version.status = KnowledgeDocumentStatus.APPROVED.value
    version.approved_by_id = user.id
    version.review_note = review_note
    document.status = KnowledgeDocumentStatus.APPROVED.value
    document.current_version_id = version.id
    document.updated_by_id = user.id

    # Rebuild the index for the newly approved version only.
    db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id).delete()
    _index_version(db, document, version)

    db.commit()
    db.refresh(version)
    audit_service.record(
        db,
        action=AuditAction.AI_KNOWLEDGE_APPROVED,
        actor_user_id=user.id,
        entity_type="knowledge_document",
        entity_id=document.id,
        company_id=document.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"version": version.version_number, "chunks": _chunk_count(db, document.id)},
    )
    return version


def _index_version(db: Session, document: KnowledgeDocument, version: KnowledgeVersion) -> None:
    """Create the searchable chunks for an approved version.

    A document is Arabic-first (``body_ar`` is required) but may also carry an
    English body. Both are indexed so an English query can retrieve an English
    document; the excerpt returned in a citation is always text the caller may
    see, so the two languages are chunked separately rather than concatenated.
    """
    bodies = [version.body_ar or ""]
    if version.body_en and version.body_en.strip() and version.body_en != version.body_ar:
        bodies.append(version.body_en)
    index = 0
    for body in bodies:
        for piece in chunk_text(
            body,
            size=settings.AI_KNOWLEDGE_CHUNK_CHARS,
            overlap=settings.AI_KNOWLEDGE_CHUNK_OVERLAP,
        ):
            db.add(
                KnowledgeChunk(
                    document_id=document.id,
                    version_id=version.id,
                    chunk_index=index,
                    content=piece,
                    search_text=normalize_arabic(piece).lower(),
                    token_count=len(tokenize(piece)),
                    company_id=document.company_id,
                    sensitivity=document.sensitivity,
                )
            )
            index += 1


def _chunk_count(db: Session, document_id: int) -> int:
    return int(
        db.execute(
            select(func.count(KnowledgeChunk.id)).where(
                KnowledgeChunk.document_id == document_id
            )
        ).scalar_one()
    )


def archive_document(
    db: Session,
    user: User,
    *,
    document_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> KnowledgeDocument:
    """Archive a document and drop its chunks so it is no longer retrievable."""
    require_permission(user, Perm.AI_KNOWLEDGE_APPROVE)
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    _require_company_scope(user, document.company_id)
    document.status = KnowledgeDocumentStatus.ARCHIVED.value
    document.updated_by_id = user.id
    db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id).delete()
    db.commit()
    db.refresh(document)
    audit_service.record(
        db,
        action=AuditAction.AI_KNOWLEDGE_ARCHIVED,
        actor_user_id=user.id,
        entity_type="knowledge_document",
        entity_id=document.id,
        company_id=document.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"slug": document.slug},
    )
    return document


def list_documents(
    db: Session, user: User, *, company_id: int | None = None, include_unapproved: bool = False
):
    """Documents the caller may see, for the management panel.

    Unlike retrieval, the panel lists drafts too (so a curator can work on
    them), but it is still bounded by the caller's company scope and the
    sensitivity ladder. Only holders of ``ai.knowledge.read`` reach it.
    """
    require_permission(user, Perm.AI_KNOWLEDGE_READ)
    stmt = select(KnowledgeDocument).order_by(KnowledgeDocument.id.desc())
    allowed = accessible_company_ids(user)
    levels = _permitted_sensitivities(user)
    stmt = stmt.where(KnowledgeDocument.sensitivity.in_(levels))
    if allowed is not None:
        # A company-scoped user sees their companies' documents plus the
        # holding-wide documents their sensitivity level already permits.
        if allowed:
            stmt = stmt.where(
                or_(
                    KnowledgeDocument.company_id.is_(None),
                    KnowledgeDocument.company_id.in_(allowed),
                )
            )
        else:
            stmt = stmt.where(KnowledgeDocument.company_id.is_(None))
    if company_id is not None:
        stmt = stmt.where(KnowledgeDocument.company_id == company_id)
    if not include_unapproved:
        stmt = stmt.where(KnowledgeDocument.status != KnowledgeDocumentStatus.ARCHIVED.value)
    return list(db.execute(stmt).scalars())


def get_document(db: Session, user: User, document_id: int) -> KnowledgeDocument:
    require_permission(user, Perm.AI_KNOWLEDGE_READ)
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    allowed = accessible_company_ids(user)
    if document.company_id is not None and allowed is not None and document.company_id not in allowed:
        raise NotFoundError("Document not found.")
    if document.sensitivity not in _permitted_sensitivities(user):
        raise NotFoundError("Document not found.")
    return document


def versions_for(db: Session, user: User, document_id: int) -> list[KnowledgeVersion]:
    document = get_document(db, user, document_id)
    return list(
        db.execute(
            select(KnowledgeVersion)
            .where(KnowledgeVersion.document_id == document.id)
            .order_by(KnowledgeVersion.version_number.desc())
        ).scalars()
    )


# --------------------------------------------------------------------------
# proposals (owner-reviewed learning loop)
# --------------------------------------------------------------------------
def raise_proposal(
    db: Session,
    user: User,
    *,
    title: str,
    proposed_body: str,
    document_id: int | None = None,
    kind: str = "correction",
    rationale: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> KnowledgeProposal:
    require_permission(user, Perm.AI_KNOWLEDGE_WRITE)
    if document_id is not None:
        # A proposal may only target a document the caller can see.
        get_document(db, user, document_id)
    proposal = KnowledgeProposal(
        document_id=document_id,
        kind=kind,
        title=title,
        proposed_body=proposed_body,
        rationale=rationale,
        status=KnowledgeProposalStatus.PENDING.value,
        raised_by_id=user.id,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    audit_service.record(
        db,
        action=AuditAction.AI_KNOWLEDGE_PROPOSAL_RAISED,
        actor_user_id=user.id,
        entity_type="knowledge_proposal",
        entity_id=proposal.id,
        company_id=None,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"kind": kind, "document_id": document_id},
    )
    return proposal


def resolve_proposal(
    db: Session,
    user: User,
    *,
    proposal_id: int,
    approve: bool,
    resolution_note: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> KnowledgeProposal:
    """Approve or reject a proposal. Approval is what applies the change."""
    require_permission(user, Perm.AI_KNOWLEDGE_MANAGE)
    proposal = db.get(KnowledgeProposal, proposal_id)
    if proposal is None:
        raise NotFoundError("Proposal not found.")
    if proposal.status != KnowledgeProposalStatus.PENDING.value:
        raise ConflictError("This proposal has already been resolved.")

    proposal.status = (
        KnowledgeProposalStatus.APPROVED.value if approve else KnowledgeProposalStatus.REJECTED.value
    )
    proposal.resolution_note = resolution_note
    proposal.resolved_by_id = user.id

    if approve and proposal.document_id is not None:
        document = db.get(KnowledgeDocument, proposal.document_id)
        if document is not None:
            version = add_version(
                db,
                user,
                document_id=document.id,
                body_ar=proposal.proposed_body,
                source_reference=f"proposal:{proposal.id}",
            )
            proposal.applied_version_id = version.id
    db.commit()
    db.refresh(proposal)
    audit_service.record(
        db,
        action=AuditAction.AI_KNOWLEDGE_PROPOSAL_RESOLVED,
        actor_user_id=user.id,
        entity_type="knowledge_proposal",
        entity_id=proposal.id,
        company_id=None,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"approved": approve},
    )
    return proposal


def list_proposals(db: Session, user: User, *, status: str | None = None):
    require_permission(user, Perm.AI_KNOWLEDGE_MANAGE)
    stmt = select(KnowledgeProposal).order_by(KnowledgeProposal.id.desc())
    if status:
        stmt = stmt.where(KnowledgeProposal.status == status)
    return list(db.execute(stmt).scalars())


# --------------------------------------------------------------------------
# knowledge-based answering
# --------------------------------------------------------------------------
def build_knowledge_context(
    db: Session, user: User, *, question: str, company_id: int | None = None
) -> dict:
    """Assemble a retrieval-grounded context for the assistant.

    Returns the retrieved sources plus a text block the provider is given. The
    sources are what the API returns as citations; the block is what the model
    may quote from, and nothing outside it.
    """
    chunks = retrieve(db, user, query=question, company_id=company_id)
    sources = [chunk.citation() for chunk in chunks]
    if chunks:
        knowledge_text = "\n\n".join(
            f"[{i + 1}] {c.title_ar}\n{c.content}" for i, c in enumerate(chunks)
        )
    else:
        knowledge_text = ""
    return {
        "scope": "knowledge",
        "period": None,
        "question": question,
        "kpis": {},
        "companies": [],
        "knowledge": sources,
        "knowledge_text": knowledge_text,
        "grounded_on_company_ids": sorted(
            {c.company_id for c in chunks if c.company_id is not None}
        ),
    }


@dataclass(slots=True)
class KnowledgeHit:
    """A retrieval hit returned to the API layer."""

    document_id: int
    title_ar: str
    title_en: str | None
    sensitivity: str
    company_id: int | None
    score: float
    excerpt: str
    source: str = field(default=KnowledgeChunkSource.LEXICAL.value)
