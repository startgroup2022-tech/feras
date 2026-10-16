"""Attachment storage.

Files are written under a single upload root using an opaque, server-generated
storage key. A client-supplied filename is never used to build a path, so a
crafted name (``../../etc/passwd``) cannot escape the root -- the classic
path-traversal flaw. Only metadata is kept in the database.

Validation is by *content type allow-list and size*, both enforced here rather
than in the UI, so the API is safe regardless of client behaviour.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from backend.core.config import settings
from backend.core.errors import ValidationError

# Extensions and MIME types the Holding accepts on a monthly report.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/csv": ".csv",
}

# --- Public website uploads (revision brief item 06) -----------------------
# Two distinct purposes, each with its own allow-list and cap:
#   * the proof-of-relationship document (internal review only), and
#   * the listing's project photos (shown only after publication).
# The caps are the brief's proposed limits, applied server-side. The image
# list is separate from the internal document list so a listing can never
# smuggle a document in as a "photo" (or the reverse).
PROOF_CONTENT_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
IMAGE_CONTENT_TYPES: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

# A CV is a document, so the image list is wrong for it; the internal document
# list lacks legacy Word (.doc), which the careers form advertises. This list
# is exactly what the form promises: PDF, DOC, DOCX.
CV_CONTENT_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

# 10 MiB, matching MAX_ATTACHMENT_BYTES.
PROOF_MAX_BYTES = 10 * 1024 * 1024
# 5 MiB per listing photo.
IMAGE_MAX_BYTES = 5 * 1024 * 1024
# 10 MiB per CV.
CV_MAX_BYTES = 10 * 1024 * 1024


def validate_cv_upload(*, filename: str, content_type: str | None, size: int) -> str:
    """Validate a careers CV and return its extension."""
    return _validate(
        filename=filename,
        content_type=content_type,
        size=size,
        allowed=CV_CONTENT_TYPES,
        max_bytes=CV_MAX_BYTES,
        limit_label="10 MB",
    )


def validate_proof_upload(*, filename: str, content_type: str | None, size: int) -> str:
    """Validate the proof-of-relationship document and return its extension."""
    return _validate(
        filename=filename,
        content_type=content_type,
        size=size,
        allowed=PROOF_CONTENT_TYPES,
        max_bytes=PROOF_MAX_BYTES,
        limit_label="10 MB",
    )


def validate_image_upload(*, filename: str, content_type: str | None, size: int) -> str:
    """Validate one listing photo and return its extension."""
    return _validate(
        filename=filename,
        content_type=content_type,
        size=size,
        allowed=IMAGE_CONTENT_TYPES,
        max_bytes=IMAGE_MAX_BYTES,
        limit_label="5 MB",
    )


def _validate(
    *,
    filename: str,
    content_type: str | None,
    size: int,
    allowed: dict[str, str],
    max_bytes: int,
    limit_label: str,
) -> str:
    if not filename or not filename.strip():
        raise ValidationError("A file name is required.")
    if size <= 0:
        raise ValidationError("The uploaded file is empty.")
    if size > max_bytes:
        raise ValidationError(f"The file exceeds the {limit_label} limit.")
    if not content_type or content_type not in allowed:
        raise ValidationError("This file type is not permitted.")
    return allowed[content_type]

# 10 MiB. Small enough to keep the demo storage honest, large enough for a
# monthly financial pack.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def upload_root() -> Path:
    root = Path(settings.UPLOAD_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_upload(*, filename: str, content_type: str | None, size: int) -> str:
    """Validate a prospective internal upload and return the extension to store."""
    return _validate(
        filename=filename,
        content_type=content_type,
        size=size,
        allowed=ALLOWED_CONTENT_TYPES,
        max_bytes=MAX_ATTACHMENT_BYTES,
        limit_label="10 MB",
    )


def store_bytes(*, data: bytes, extension: str) -> str:
    """Write bytes to the upload root under a fresh opaque key; return the key."""
    key = f"{uuid.uuid4().hex}{extension}"
    destination = upload_root() / key
    with open(destination, "wb") as handle:
        handle.write(data)
    return key


def resolve_stored_path(storage_key: str) -> Path:
    """Resolve a storage key to a path, refusing anything outside the root.

    Defence in depth: keys are server-generated, but this guard means even a
    corrupted database row cannot be used to read an arbitrary file.
    """
    root = upload_root()
    candidate = (root / storage_key).resolve()
    if os.path.commonpath([str(root), str(candidate)]) != str(root):
        raise ValidationError("Invalid storage key.")
    if not candidate.is_file():
        from backend.core.errors import NotFoundError

        raise NotFoundError("Attachment file not found.")
    return candidate


def delete_stored(storage_key: str) -> None:
    try:
        path = resolve_stored_path(storage_key)
    except Exception:  # noqa: BLE001 - best-effort cleanup, never fatal
        return
    path.unlink(missing_ok=True)
