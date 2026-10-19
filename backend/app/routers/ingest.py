from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_user, utcnow
from ..db import get_db
from ..devices import detect_and_ingest
from ..models import TrackedPitcher, User
from ..schemas import IngestResult

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/csv", response_model=IngestResult)
@router.post("/statcast", response_model=IngestResult, include_in_schema=False)  # older name
async def upload_csv(file: UploadFile, db: Session = Depends(get_db),
                     user: User = Depends(require_user)):
    """Upload a TrackMan or Rapsodo session export, or a Baseball Savant / Statcast CSV (or your
    own file using Statcast's columns). The format is detected from the header.

    Pitchers are matched by name among your own pitchers; new ones are created as yours and
    added to your dashboard.
    """
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (50 MB max)")
    try:
        result = detect_and_ingest(db, content, owner_id=user.id)
    except (UnicodeDecodeError, ValueError) as e:
        db.rollback()
        raise HTTPException(400, f"Could not parse CSV: {e}")
    tracked = set(db.scalars(select(TrackedPitcher.pitcher_id)
                             .where(TrackedPitcher.user_id == user.id)))
    for pid in result.pop("pitcher_ids"):
        if pid not in tracked:
            db.add(TrackedPitcher(user_id=user.id, pitcher_id=pid, created_at=utcnow()))
    db.commit()
    return result
