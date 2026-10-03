"""Document storage.

Reuses the project's existing upload root and its path-traversal guard, but
with a broader allow-list for the document-management module. The rules are the
same as for report attachments:

* the client filename is never used to build a path -- the stored key is a
  fresh opaque UUID plus a *server-derived* extension;
* type and size are validated on the server;
* resolving a key refuses anything outside the upload root.

This module adds document-specific limits and an explicit ``reject executables``
rule so a ``.exe``/``.sh``/``.php`` cannot be uploaded under a permissive MIME
type.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from backend.core.config import settings
from backend.core.errors import NotFoundError, ValidationError

# Allowed content types -> canonical extension. Deliberately excludes
# ``text/html`` and anything script-like.
ALLOWED_DOCUMENT_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/tiff": ".tiff",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-excel": ".xls",
    "application/msword": ".doc",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/zip": ".zip",
}

# Extensions that are never acceptable regardless of the declared MIME type.
FORBIDDEN_EXTENSIONS = {
    ".exe", ".sh", ".bat", ".cmd", ".com", ".msi", ".dll", ".so",
    ".js", ".mjs", ".php", ".py", ".rb", ".pl", ".jsp", ".asp", ".aspx",
    ".html", ".htm", ".svg",  # SVG can carry script; excluded deliberately
}

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024  # 25 MiB


def document_root() -> Path:
    root = Path(settings.UPLOAD_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_document(
    *, filename: str, content_type: str | None, size: int
) -> str:
    """Validate an upload and return the canonical extension to store.

    The *client* filename is only inspected to detect a dangerous extension; it
    is never used to build the destination path.
    """
    if not filename or not filename.strip():
        raise ValidationError("A file name is required.")
    if size <= 0:
        raise ValidationError("The uploaded file is empty.")
    if size > MAX_DOCUMENT_BYTES:
        raise ValidationError("The file exceeds the 25 MB limit.")

    lowered = filename.lower()
    for forbidden in FORBIDDEN_EXTENSIONS:
        if lowered.endswith(forbidden):
            raise ValidationError("This file type is not permitted.")

    if not content_type or content_type not in ALLOWED_DOCUMENT_TYPES:
        raise ValidationError("This file type is not permitted.")
    return ALLOWED_DOCUMENT_TYPES[content_type]


def store_document_bytes(*, data: bytes, extension: str) -> str:
    """Persist bytes under a fresh opaque key; return the key (no path)."""
    key = f"{uuid.uuid4().hex}{extension}"
    destination = document_root() / key
    # Defence in depth: the key is server-generated, so this cannot fire, but
    # it guarantees we never write outside the root even if that changes.
    if os.path.commonpath([str(document_root()), str(destination.resolve())]) != str(
        document_root()
    ):
        raise ValidationError("Invalid storage key.")
    with open(destination, "wb") as handle:
        handle.write(data)
    return key


def resolve_document_path(storage_key: str) -> Path:
    """Resolve a key to a real path, refusing traversal and missing files."""
    root = document_root()
    candidate = (root / storage_key).resolve()
    if os.path.commonpath([str(root), str(candidate)]) != str(root):
        raise ValidationError("Invalid storage key.")
    if not candidate.is_file():
        raise NotFoundError("Document file not found.")
    return candidate


def delete_document_bytes(storage_key: str) -> None:
    try:
        path = resolve_document_path(storage_key)
    except Exception:  # noqa: BLE001 - best-effort cleanup, never fatal
        return
    path.unlink(missing_ok=True)


__all__ = [
    "ALLOWED_DOCUMENT_TYPES",
    "FORBIDDEN_EXTENSIONS",
    "MAX_DOCUMENT_BYTES",
    "document_root",
    "validate_document",
    "store_document_bytes",
    "resolve_document_path",
    "delete_document_bytes",
]
