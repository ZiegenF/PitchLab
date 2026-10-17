from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import analytics
from ..access import flags, get_editable, get_visible, tracked_ids, visible_filter
from ..auth import current_user, require_user, utcnow
from ..db import get_db
from ..insights import build_insights, evaluate_goal
from ..models import Appearance, Goal, Pitch, Pitcher, TrackedPitcher, User
from ..photos import MAX_PHOTO_BYTES, image_ext, remove_photo, save_photo
from ..schemas import (AppearanceOut, GameCreate, GoalIn, GoalOut, PitchOut, PitcherCreate,
                       PitcherListItem, PitcherOut, PitcherUpdate, StatDefinition)

router = APIRouter(prefix="/api", tags=["pitchers"])


def _commit_or_409(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, message)


def normalize_level(pitcher: Pitcher) -> None:
    """Drop fields that don't apply at the pitcher's level (only college players can be in the
    portal; class years are for high school and college)."""
    if pitcher.level != "NCAA":
        pitcher.in_portal = False
    if pitcher.level not in ("HS", "NCAA"):
        pitcher.class_year = None


def pitcher_out(pitcher: Pitcher, user: User | None, tracked: set[int]) -> PitcherOut:
    return PitcherOut.model_validate(pitcher).model_copy(update=flags(pitcher, user, tracked))


@router.get("/stats", response_model=list[StatDefinition], tags=["stats"])
def stat_definitions():
    """Every stat the API computes, with labels and formatting hints for the UI."""
    return [s.definition() for s in analytics.STATS]


@router.get("/pitchers", response_model=list[PitcherListItem])
def list_pitchers(level: list[str] = Query(default=[], description="e.g. ?level=AAA&level=AA"),
                  portal: bool = Query(False, description="Only college players in the transfer portal"),
                  db: Session = Depends(get_db), user: User | None = Depends(current_user)):
    """League pitchers plus, when signed in, your own."""
    query = select(Pitcher).where(visible_filter(user))
    if level:
        query = query.where(Pitcher.level.in_(level))
    if portal:
        query = query.where(Pitcher.in_portal.is_(True))
    pitchers = db.scalars(
        query.options(selectinload(Pitcher.appearances)).order_by(Pitcher.name)
    ).all()
    fb_velo = dict(db.execute(
        select(Pitch.pitcher_id, func.avg(Pitch.velocity))
        .where(Pitch.pitch_type.in_(analytics.FASTBALLS))
        .group_by(Pitch.pitcher_id)
    ).all())
    tracked = tracked_ids(db, user)
    out = []
    for p in pitchers:
        s = analytics.compute_stats({**analytics.box_score_totals(p.appearances), "pitches": 0},
                                    group="traditional")
        velo = fb_velo.get(p.id)
        out.append(PitcherListItem(
            **pitcher_out(p, user, tracked).model_dump(),
            games=s["games"], innings_pitched=s["innings_pitched"], era=s["era"],
            k_per_9=s["k_per_9"], whip=s["whip"],
            avg_fb_velo=round(velo, 1) if velo is not None else None,
        ))
    return out


@router.post("/pitchers", response_model=PitcherOut, status_code=201)
def create_pitcher(body: PitcherCreate, db: Session = Depends(get_db),
                   user: User = Depends(require_user)):
    """Add a private pitcher to your account. It's tracked on your dashboard automatically."""
    pitcher = Pitcher(**body.model_dump(), owner_id=user.id)
    normalize_level(pitcher)
    db.add(pitcher)
    _commit_or_409(db, f"You already have a pitcher named '{body.name}'")
    db.add(TrackedPitcher(user_id=user.id, pitcher_id=pitcher.id, created_at=utcnow()))
    db.commit()
    return pitcher_out(pitcher, user, {pitcher.id})


@router.get("/pitchers/{pitcher_id}")
def pitcher_dashboard(pitcher_id: int, db: Session = Depends(get_db),
                      user: User | None = Depends(current_user)):
    """Bio, season stats, and recent-form stats (see GET /api/stats for labels)."""
    pitcher = get_visible(db, pitcher_id, user)
    windows = analytics.season_and_recent(db, pitcher)
    return {
        "pitcher": pitcher_out(pitcher, user, tracked_ids(db, user)),
        "stats": windows["season"],
        "recent": windows["recent"],
        "recent_games": windows["recent_games"],
    }


@router.patch("/pitchers/{pitcher_id}", response_model=PitcherOut)
def update_pitcher(pitcher_id: int, body: PitcherUpdate, db: Session = Depends(get_db),
                   user: User | None = Depends(current_user)):
    pitcher = get_editable(db, pitcher_id, user)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(pitcher, k, v)
    normalize_level(pitcher)
    _commit_or_409(db, f"You already have a pitcher named '{body.name}'")
    return pitcher_out(pitcher, user, tracked_ids(db, user))


@router.delete("/pitchers/{pitcher_id}", status_code=204)
def delete_pitcher(pitcher_id: int, db: Session = Depends(get_db),
                   user: User | None = Depends(current_user)):
    pitcher = get_editable(db, pitcher_id, user)
    remove_photo(pitcher)
    db.delete(pitcher)
    db.commit()


@router.post("/pitchers/{pitcher_id}/photo", response_model=PitcherOut)
async def upload_photo(pitcher_id: int, file: UploadFile, db: Session = Depends(get_db),
                       user: User | None = Depends(current_user)):
    pitcher = get_editable(db, pitcher_id, user)
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photo too large (5 MB max)")
    ext = image_ext(data)
    if ext is None:
        raise HTTPException(400, "Photo must be a JPEG, PNG, GIF or WebP image")
    save_photo(pitcher, data, ext)
    db.commit()
    return pitcher_out(pitcher, user, tracked_ids(db, user))


@router.delete("/pitchers/{pitcher_id}/photo", response_model=PitcherOut)
def delete_photo(pitcher_id: int, db: Session = Depends(get_db),
                 user: User | None = Depends(current_user)):
    pitcher = get_editable(db, pitcher_id, user)
    remove_photo(pitcher)
    db.commit()
    return pitcher_out(pitcher, user, tracked_ids(db, user))


@router.get("/pitchers/{pitcher_id}/arsenal")
def pitcher_arsenal(pitcher_id: int, db: Session = Depends(get_db),
                    user: User | None = Depends(current_user)):
    get_visible(db, pitcher_id, user)
    return analytics.arsenal(db, pitcher_id)


@router.get("/pitchers/{pitcher_id}/trend")
def pitcher_trend(pitcher_id: int, db: Session = Depends(get_db),
                  user: User | None = Depends(current_user)):
    get_visible(db, pitcher_id, user)
    return analytics.velocity_trend(db, pitcher_id)


@router.get("/pitchers/{pitcher_id}/insights")
def pitcher_insights(pitcher_id: int, db: Session = Depends(get_db),
                     user: User | None = Depends(current_user)):
    """Coach's Corner: what's trending the wrong way (and what to do), and what's working."""
    return build_insights(db, get_visible(db, pitcher_id, user))


def goal_out(goal: Goal, windows: dict) -> GoalOut:
    return GoalOut(id=goal.id, pitcher_id=goal.pitcher_id, stat_key=goal.stat_key,
                   target=goal.target, **evaluate_goal(goal.stat_key, goal.target, windows))


@router.get("/pitchers/{pitcher_id}/goals", response_model=list[GoalOut])
def list_goals(pitcher_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    pitcher = get_visible(db, pitcher_id, user)
    goals = db.scalars(select(Goal).where(Goal.user_id == user.id, Goal.pitcher_id == pitcher_id)
                       .order_by(Goal.id)).all()
    windows = analytics.season_and_recent(db, pitcher)
    return [goal_out(g, windows) for g in goals]


@router.post("/pitchers/{pitcher_id}/goals", response_model=GoalOut, status_code=201)
def add_goal(pitcher_id: int, body: GoalIn, db: Session = Depends(get_db),
             user: User = Depends(require_user)):
    pitcher = get_visible(db, pitcher_id, user)
    stat = analytics.STATS_BY_KEY.get(body.stat_key)
    if stat is None or stat.better is None:
        raise HTTPException(422, "Goals need a stat with a better direction (e.g. ERA, K%)")
    goal = Goal(user_id=user.id, pitcher_id=pitcher_id, stat_key=body.stat_key,
                target=body.target, created_at=utcnow())
    db.add(goal)
    if pitcher_id not in tracked_ids(db, user):  # setting a goal implies following the pitcher
        db.add(TrackedPitcher(user_id=user.id, pitcher_id=pitcher_id, created_at=utcnow()))
    db.commit()
    return goal_out(goal, analytics.season_and_recent(db, pitcher))


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    goal = db.get(Goal, goal_id)
    if goal is None or goal.user_id != user.id:
        raise HTTPException(404, "Goal not found")
    db.delete(goal)
    db.commit()


def _appearance_out(a: Appearance, pitches: int) -> AppearanceOut:
    return AppearanceOut(
        **{c: getattr(a, c) for c in (
            "id", "game_date", "opponent", "is_start", "hits", "runs", "earned_runs",
            "walks", "strikeouts", "home_runs", "batters_faced")},
        innings_pitched=analytics.innings_display(a.outs),
        pitches=pitches,
    )


@router.get("/pitchers/{pitcher_id}/games", response_model=list[AppearanceOut])
def pitcher_games(pitcher_id: int, db: Session = Depends(get_db),
                  user: User | None = Depends(current_user)):
    get_visible(db, pitcher_id, user)
    counts = dict(db.execute(
        select(Pitch.appearance_id, func.count(Pitch.id))
        .where(Pitch.pitcher_id == pitcher_id)
        .group_by(Pitch.appearance_id)
    ).all())
    apps = db.scalars(
        select(Appearance).where(Appearance.pitcher_id == pitcher_id)
        .order_by(Appearance.game_date.desc())
    ).all()
    return [_appearance_out(a, counts.get(a.id, 0)) for a in apps]


@router.post("/pitchers/{pitcher_id}/games", response_model=AppearanceOut, status_code=201)
def add_game(pitcher_id: int, body: GameCreate, db: Session = Depends(get_db),
             user: User | None = Depends(current_user)):
    """Enter a box-score line by hand, e.g. from a scorebook."""
    get_editable(db, pitcher_id, user)
    if body.earned_runs > body.runs:
        raise HTTPException(422, "Earned runs can't exceed runs")
    fields = body.model_dump(exclude={"innings_pitched", "batters_faced"})
    fields["opponent"] = fields["opponent"].strip().upper()
    # outs + baserunners is a floor on batters faced (misses errors and fielder's choices)
    bf = body.batters_faced
    if bf is None:
        bf = body.outs + body.hits + body.walks + body.hit_by_pitch
    app = Appearance(pitcher_id=pitcher_id, outs=body.outs, batters_faced=bf, **fields)
    db.add(app)
    _commit_or_409(db, f"A game on {body.game_date} vs {body.opponent or '(none)'} already exists")
    return _appearance_out(app, 0)


@router.delete("/pitchers/{pitcher_id}/games/{game_id}", status_code=204)
def delete_game(pitcher_id: int, game_id: int, db: Session = Depends(get_db),
                user: User | None = Depends(current_user)):
    get_editable(db, pitcher_id, user)
    app = db.get(Appearance, game_id)
    if app is None or app.pitcher_id != pitcher_id:
        raise HTTPException(404, "Game not found")
    db.delete(app)
    db.commit()


@router.get("/pitchers/{pitcher_id}/pitches", response_model=list[PitchOut])
def pitcher_pitches(
    pitcher_id: int,
    pitch_type: str | None = None,
    appearance_id: int | None = None,
    limit: int = Query(2000, le=10000),
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
):
    """Raw pitches for location / movement plots."""
    get_visible(db, pitcher_id, user)
    q = select(Pitch).where(Pitch.pitcher_id == pitcher_id)
    if pitch_type:
        q = q.where(Pitch.pitch_type == pitch_type)
    if appearance_id:
        q = q.where(Pitch.appearance_id == appearance_id)
    return db.scalars(q.order_by(Pitch.id.desc()).limit(limit)).all()
