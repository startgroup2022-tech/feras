"""Website media storage.

Mirrors the branding storage discipline but for the general media library:
an opaque server-generated key, a server-derived extension, an allow-list of
image/document types and a path-traversal guard on resolve. SVG is excluded
from *public* media because it can carry script and is rendered inline on the
public site.

Assets live under ``<UPLOAD_DIR>/website``. The database stores only the key
and metadata; the public endpoint filters on the row's ``visibility`` so a
private asset can never be streamed anonymously.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from backend.core.config import settings
from backend.core.errors import NotFoundError, ValidationError

# Content type -> canonical extension. Raster images plus the document types a
# marketing page legitimately links to. No SVG, no HTML, no executable types.
ALLOWED_MEDIA_TYPES: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "application/pdf": ".pdf",
}

MAX_MEDIA_BYTES = 8 * 1024 * 1024


def media_root() -> Path:
    root = Path(settings.UPLOAD_DIR).resolve() / "website"
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_media(
    *, filename: str, content_type: str | None, size: int
) -> str:
    """Validate a prospective upload and return the extension to store."""
    if not filename or not filename.strip():
        raise ValidationError("A file name is required.")
    if size <= 0:
        raise ValidationError("The uploaded file is empty.")
    if size > MAX_MEDIA_BYTES:
        raise ValidationError("The file exceeds the 8 MB limit.")
    if not content_type or content_type not in ALLOWED_MEDIA_TYPES:
        raise ValidationError("This file type is not permitted.")
    return ALLOWED_MEDIA_TYPES[content_type]


def store_media_bytes(*, data: bytes, extension: str) -> str:
    """Persist bytes under a fresh opaque key; return the key (never a path)."""
    root = media_root()
    key = f"{uuid.uuid4().hex}{extension}"
    destination = root / key
    if os.path.commonpath([str(root), str(destination.resolve())]) != str(root):
        raise ValidationError("Invalid storage key.")
    with open(destination, "wb") as handle:
        handle.write(data)
    return key


def resolve_media_path(storage_key: str) -> Path:
    """Resolve a key to a real path, refusing traversal and missing files."""
    root = media_root()
    candidate = (root / storage_key).resolve()
    if os.path.commonpath([str(root), str(candidate)]) != str(root):
        raise ValidationError("Invalid storage key.")
    if not candidate.is_file():
        raise NotFoundError("Media asset not found.")
    return candidate


def delete_media_bytes(storage_key: str) -> None:
    try:
        path = resolve_media_path(storage_key)
    except Exception:  # noqa: BLE001 - best-effort cleanup, never fatal
        return
    path.unlink(missing_ok=True)


__all__ = [
    "ALLOWED_MEDIA_TYPES",
    "MAX_MEDIA_BYTES",
    "delete_media_bytes",
    "media_root",
    "resolve_media_path",
    "store_media_bytes",
    "validate_media",
]
