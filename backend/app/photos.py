"""Pitcher photo storage on local disk (swap for S3 or similar when deploying)."""

import os
import uuid
from pathlib import Path

from .models import Pitcher

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
PHOTO_DIR = UPLOAD_DIR / "pitchers"
MAX_PHOTO_BYTES = 5 * 1024 * 1024
# detect the format from the file's first bytes rather than trusting the browser's content type
IMAGE_SIGNATURES = {b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png", b"GIF8": ".gif"}


def image_ext(data: bytes) -> str | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return next((ext for sig, ext in IMAGE_SIGNATURES.items() if data.startswith(sig)), None)


def save_photo(pitcher: Pitcher, data: bytes, ext: str) -> None:
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{pitcher.id}-{uuid.uuid4().hex[:8]}{ext}"  # new name per upload busts caches
    (PHOTO_DIR / filename).write_bytes(data)
    remove_photo(pitcher)
    pitcher.photo_url = f"/uploads/pitchers/{filename}"


def remove_photo(pitcher: Pitcher) -> None:
    if pitcher.photo_url and pitcher.photo_url.startswith("/uploads/"):
        (PHOTO_DIR / Path(pitcher.photo_url).name).unlink(missing_ok=True)
    pitcher.photo_url = None
