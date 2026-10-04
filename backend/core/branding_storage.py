"""Website branding asset storage (the Holding logo).

Reuses the project's upload root and its path-traversal guard, but with a
branding-specific allow-list: only raster images are accepted. SVG is
deliberately excluded because it can carry script and is rendered inside the
public header on every page.

The stored key is always a fresh opaque UUID plus a *server-derived*
extension, so a client filename can never influence the path. Resolving a key
refuses anything outside the upload root.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from backend.core.config import settings
from backend.core.errors import NotFoundError, ValidationError

# Content type -> canonical extension. Raster only; no SVG.
ALLOWED_BRANDING_TYPES: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

# A logo is small by nature. 4 MiB is generous for a high-resolution source
# while keeping the public header light.
MAX_BRANDING_BYTES = 4 * 1024 * 1024


def branding_root() -> Path:
    root = Path(settings.UPLOAD_DIR).resolve() / "branding"
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_branding_image(
    *, filename: str, content_type: str | None, size: int
) -> str:
    """Validate a prospective logo upload and return the extension to store."""
    if not filename or not filename.strip():
        raise ValidationError("A file name is required.")
    if size <= 0:
        raise ValidationError("The uploaded file is empty.")
    if size > MAX_BRANDING_BYTES:
        raise ValidationError("The logo exceeds the 4 MB limit.")
    if not content_type or content_type not in ALLOWED_BRANDING_TYPES:
        raise ValidationError("Only PNG, JPEG, WebP or GIF images are permitted.")
    return ALLOWED_BRANDING_TYPES[content_type]


def store_branding_bytes(*, data: bytes, extension: str) -> str:
    """Persist logo bytes under a fresh opaque key; return the key (no path)."""
    key = f"{uuid.uuid4().hex}{extension}"
    destination = branding_root() / key
    if os.path.commonpath(
        [str(branding_root()), str(destination.resolve())]
    ) != str(branding_root()):
        raise ValidationError("Invalid storage key.")
    with open(destination, "wb") as handle:
        handle.write(data)
    return key


def resolve_branding_path(storage_key: str) -> Path:
    """Resolve a key to a real path, refusing traversal and missing files."""
    root = branding_root()
    candidate = (root / storage_key).resolve()
    if os.path.commonpath([str(root), str(candidate)]) != str(root):
        raise ValidationError("Invalid storage key.")
    if not candidate.is_file():
        raise NotFoundError("Branding asset not found.")
    return candidate


def delete_branding_bytes(storage_key: str) -> None:
    try:
        path = resolve_branding_path(storage_key)
    except Exception:  # noqa: BLE001 - best-effort cleanup, never fatal
        return
    path.unlink(missing_ok=True)


__all__ = [
    "ALLOWED_BRANDING_TYPES",
    "MAX_BRANDING_BYTES",
    "branding_root",
    "validate_branding_image",
    "store_branding_bytes",
    "resolve_branding_path",
    "delete_branding_bytes",
]
