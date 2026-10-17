"""The signed-in user's dashboard: tracked pitchers, tile preferences, goals."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from .. import analytics
from ..access import get_visible
from ..auth import require_user, utcnow
from ..db import get_db
from ..insights import build_insights
from ..models import Goal, Pitcher, TrackedPitcher, User
from ..schemas import PitcherOut, PreferencesIn, UserOut
from .pitchers import goal_out

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Every tracked pitcher with season + recent stats, top insight and goals."""
    rows = db.execute(
        select(Pitcher, TrackedPitcher.created_at)
        .join(TrackedPitcher, TrackedPitcher.pitcher_id == Pitcher.id)
        .where(TrackedPitcher.user_id == user.id)
        .options(selectinload(Pitcher.appearances))
        .order_by(TrackedPitcher.created_at)
    ).all()
    goals_by_pitcher: dict[int, list[Goal]] = {}
    for g in db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.id)):
        goals_by_pitcher.setdefault(g.pitcher_id, []).append(g)

    players = []
    for pitcher, _ in rows:
        windows = analytics.season_and_recent(db, pitcher)
        insights = build_insights(db, pitcher, windows)["items"]
        needs_work = [i for i in insights if i["kind"] in ("declining", "pitch_mix")]
        players.append({
            "pitcher": PitcherOut.model_validate(pitcher).model_copy(update={
                "is_mine": pitcher.owner_id == user.id, "is_public": pitcher.owner_id is None,
                "is_tracked": True}),
            "season": windows["season"],
            "recent": windows["recent"],
            "recent_games": windows["recent_games"],
            "focus": needs_work[0] if needs_work else None,
            "improving": sum(i["kind"] == "improving" for i in insights),
            "needs_work": len(needs_work),
            "goals": [goal_out(g, windows) for g in goals_by_pitcher.get(pitcher.id, [])],
        })
    return {"players": players}


@router.put("/tracked/{pitcher_id}", status_code=204)
def track(pitcher_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    get_visible(db, pitcher_id, user)
    exists = db.scalar(select(TrackedPitcher).where(TrackedPitcher.user_id == user.id,
                                                    TrackedPitcher.pitcher_id == pitcher_id))
    if not exists:
        db.add(TrackedPitcher(user_id=user.id, pitcher_id=pitcher_id, created_at=utcnow()))
        db.commit()


@router.delete("/tracked/{pitcher_id}", status_code=204)
def untrack(pitcher_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    db.execute(delete(TrackedPitcher).where(TrackedPitcher.user_id == user.id,
                                            TrackedPitcher.pitcher_id == pitcher_id))
    db.commit()


@router.put("/preferences", response_model=UserOut)
def set_preferences(body: PreferencesIn, db: Session = Depends(get_db),
                    user: User = Depends(require_user)):
    if body.tiles is not None:
        unknown = [k for k in body.tiles if k not in analytics.STATS_BY_KEY]
        if unknown:
            raise HTTPException(422, f"Unknown stats: {', '.join(unknown)}")
    # assign a new dict: SQLAlchemy doesn't notice in-place changes to a JSON column
    user.preferences = {**(user.preferences or {}), "tiles": body.tiles}
    db.commit()
    return user
