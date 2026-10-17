"""Who can see and change which pitchers.

Public pitchers (owner_id NULL, the league data) are visible to everyone and read-only.
Private pitchers are visible to and editable by their owner only; to anyone else they 404.
"""

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .models import Pitcher, TrackedPitcher, User


def visible_filter(user: User | None):
    if user is None:
        return Pitcher.owner_id.is_(None)
    return or_(Pitcher.owner_id.is_(None), Pitcher.owner_id == user.id)


def get_visible(db: Session, pitcher_id: int, user: User | None) -> Pitcher:
    pitcher = db.scalar(
        select(Pitcher).where(Pitcher.id == pitcher_id, visible_filter(user))
        .options(selectinload(Pitcher.appearances))
    )
    if pitcher is None:
        raise HTTPException(404, "Pitcher not found")
    return pitcher


def get_editable(db: Session, pitcher_id: int, user: User | None) -> Pitcher:
    pitcher = get_visible(db, pitcher_id, user)
    if user is None or pitcher.owner_id != user.id:
        raise HTTPException(403, "League pitchers are read-only. Add your own to edit them.")
    return pitcher


def tracked_ids(db: Session, user: User | None) -> set[int]:
    if user is None:
        return set()
    return set(db.scalars(select(TrackedPitcher.pitcher_id).where(TrackedPitcher.user_id == user.id)))


def flags(pitcher: Pitcher, user: User | None, tracked: set[int]) -> dict:
    return {
        "is_mine": user is not None and pitcher.owner_id == user.id,
        "is_public": pitcher.owner_id is None,
        "is_tracked": pitcher.id in tracked,
    }
