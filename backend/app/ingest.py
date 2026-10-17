"""Ingest Statcast-format pitch rows (Baseball Savant CSV export) and derive box-score lines.

Works on a real Savant export (https://baseballsavant.mlb.com/statcast_search -> "Download CSV")
or on rows produced by `seed.py`. Columns used:

    player_name, game_date, pitch_type, release_speed, release_spin_rate, plate_x, plate_z,
    description, events, inning, balls, strikes, inning_topbot, home_team, away_team,
    p_throws, bat_score, post_bat_score

Statcast has no earned/unearned split, so all runs are treated as earned.
"""

import csv
import io
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Appearance, Pitch, Pitcher

DESCRIPTION_MAP = {
    "ball": "ball", "blocked_ball": "ball", "pitchout": "ball", "intent_ball": "ball",
    "automatic_ball": "ball",
    "called_strike": "called_strike", "automatic_strike": "called_strike",
    "swinging_strike": "swinging_strike", "swinging_strike_blocked": "swinging_strike",
    "foul_tip": "swinging_strike", "missed_bunt": "swinging_strike",
    "foul": "foul", "foul_bunt": "foul", "bunt_foul_tip": "foul", "foul_pitchout": "foul",
    "hit_into_play": "in_play", "hit_into_play_no_out": "in_play", "hit_into_play_score": "in_play",
    "hit_by_pitch": "hit_by_pitch",
}

HIT_EVENTS = {"single", "double", "triple", "home_run"}
WALK_EVENTS = {"walk", "intent_walk"}
OUTS_BY_EVENT = {
    "field_out": 1, "force_out": 1, "sac_fly": 1, "sac_bunt": 1, "fielders_choice_out": 1,
    "other_out": 1, "strikeout": 1, "grounded_into_double_play": 2, "double_play": 2,
    "strikeout_double_play": 2, "sac_fly_double_play": 2, "sac_bunt_double_play": 2,
    "triple_play": 3, "caught_stealing_2b": 1, "caught_stealing_3b": 1, "caught_stealing_home": 1,
    "pickoff_1b": 1, "pickoff_2b": 1, "pickoff_3b": 1, "pickoff_caught_stealing_2b": 1,
    "pickoff_caught_stealing_3b": 1, "pickoff_caught_stealing_home": 1,
}
NON_PA_PREFIXES = ("caught_stealing", "pickoff", "stolen_base", "wild_pitch", "passed_ball",
                   "other_advance", "game_advisory", "balk")


def _f(v) -> float | None:
    try:
        return float(v) if v not in (None, "", "NA", "null") else None
    except ValueError:
        return None


def _i(v, default: int = 0) -> int:
    f = _f(v)
    return int(f) if f is not None else default


def _name(raw: str) -> str:
    """Savant uses 'Last, First'; store 'First Last'."""
    raw = (raw or "").strip()
    if "," in raw:
        last, first = (p.strip() for p in raw.split(",", 1))
        return f"{first} {last}"
    return raw


def _teams(row: dict) -> tuple[str, str]:
    """Return (pitcher_team, opponent). Top of the inning -> home team is pitching."""
    if row.get("inning_topbot") and row.get("home_team"):
        home, away = row["home_team"], row.get("away_team", "")
        return (home, away) if row["inning_topbot"].lower().startswith("top") else (away, home)
    return row.get("team", ""), row.get("opponent", "")


def ingest_rows(db: Session, rows: list[dict], owner_id: int | None = None,
                role_hint: dict[str, str] | None = None) -> dict:
    """owner_id None loads public league data; otherwise pitchers are private to that user."""
    games: dict[tuple, list[dict]] = defaultdict(list)
    skipped = 0
    for row in rows:
        name, game_date = _name(row.get("player_name", "")), row.get("game_date", "")
        if not name or not game_date:
            skipped += 1
            continue
        _, opp = _teams(row)
        games[(name, game_date[:10], opp)].append(row)

    pitchers: dict[str, Pitcher] = {}
    n_pitches = 0
    for (name, gdate, opp), game_rows in games.items():
        owner_match = Pitcher.owner_id.is_(None) if owner_id is None else Pitcher.owner_id == owner_id
        pitcher = pitchers.get(name) or db.scalar(
            select(Pitcher).where(Pitcher.name == name, owner_match))
        if pitcher is None:
            first = game_rows[0]
            pitcher = Pitcher(
                owner_id=owner_id,
                name=name,
                team=_teams(first)[0],
                throws=(first.get("p_throws") or "R")[:1],
                role=(role_hint or {}).get(name, "SP"),
            )
            db.add(pitcher)
            db.flush()
        pitchers[name] = pitcher

        gd = date.fromisoformat(gdate)
        app = db.scalar(select(Appearance).where(
            Appearance.pitcher_id == pitcher.id, Appearance.game_date == gd, Appearance.opponent == opp
        ))
        if app is None:
            app = Appearance(pitcher_id=pitcher.id, game_date=gd, opponent=opp)
            db.add(app)
        else:  # re-ingesting the same game replaces it
            app.pitches.clear()
        _fill_box_score(app, game_rows)
        db.flush()

        db.add_all(Pitch(
            appearance_id=app.id,
            pitcher_id=pitcher.id,
            pitch_type=(r.get("pitch_type") or "UN")[:4],
            velocity=_f(r.get("release_speed")),
            spin_rate=_f(r.get("release_spin_rate")),
            plate_x=_f(r.get("plate_x")),
            plate_z=_f(r.get("plate_z")),
            result=DESCRIPTION_MAP.get(r.get("description", ""), "ball"),
            inning=_i(r.get("inning"), 1),
            balls=_i(r.get("balls")),
            strikes=_i(r.get("strikes")),
        ) for r in game_rows)
        n_pitches += len(game_rows)

    db.commit()
    return {"pitchers": len(pitchers), "appearances": len(games), "pitches": n_pitches,
            "skipped_rows": skipped, "pitcher_ids": [p.id for p in pitchers.values()]}


def _fill_box_score(app: Appearance, rows: list[dict]) -> None:
    box = dict.fromkeys(("outs", "hits", "runs", "walks", "strikeouts", "home_runs",
                         "hit_by_pitch", "batters_faced"), 0)
    for r in rows:
        ev = (r.get("events") or "").strip()
        if r.get("bat_score") not in (None, "") and r.get("post_bat_score") not in (None, ""):
            box["runs"] += max(0, _i(r["post_bat_score"]) - _i(r["bat_score"]))
        if not ev:
            continue
        box["outs"] += OUTS_BY_EVENT.get(ev, 0)
        if ev.startswith(NON_PA_PREFIXES):
            continue
        box["batters_faced"] += 1
        box["hits"] += ev in HIT_EVENTS
        box["home_runs"] += ev == "home_run"
        box["walks"] += ev in WALK_EVENTS
        box["strikeouts"] += ev.startswith("strikeout")
        box["hit_by_pitch"] += ev == "hit_by_pitch"
    for k, v in box.items():
        setattr(app, k, v)
    app.earned_runs = box["runs"]
    app.is_start = min(_i(r.get("inning"), 1) for r in rows) == 1


def ingest_csv(db: Session, content: bytes, owner_id: int | None = None) -> dict:
    text = content.decode("utf-8-sig")
    return ingest_rows(db, list(csv.DictReader(io.StringIO(text))), owner_id=owner_id)
