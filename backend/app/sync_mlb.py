"""Sync real pitchers from MLB data, then check the result against official totals.

    python -m app.sync_mlb "Tarik Skubal" --season 2024
    python -m app.sync_mlb --id 669373 --season 2024
    python -m app.sync_mlb --refresh            # re-sync every MLB pitcher already loaded

Each stat comes from the source that owns it:
  - box scores (IP, H, R, ER, BB, K, HR, BF) from the MLB Stats API game log, i.e. the official
    scorer, at every level from Single-A to MLB
  - pitch-level data (velocity, spin, location, results) from Statcast, MLB games only,
    attached to the official games by game_pk

After loading, `reconcile` re-adds our stored games and compares them with MLB's official season
line at each level, plus Statcast pitches loaded vs the official pitch count. The result is
saved on the pitcher (Pitcher.verification) and shown in the UI, so a mismatch can't go unseen.

Synced pitchers are public league data. One season per pitcher: syncing another season
replaces the previous one, so "season" stats always mean one season.
"""

import argparse
from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import analytics
from .auth import utcnow
from .ingest import pitch_from_row, thrown
from .mlb import HEADSHOT, SPORT_LEVELS, MlbClient
from .models import BOX_OFFICIAL, SOURCE_MLB, Appearance, Pitch, Pitcher

# our box-score field -> Stats API field
BOX_FIELDS = {
    "outs": "outs", "hits": "hits", "runs": "runs", "earned_runs": "earnedRuns",
    "walks": "baseOnBalls", "strikeouts": "strikeOuts", "home_runs": "homeRuns",
    "hit_by_pitch": "hitByPitch", "batters_faced": "battersFaced",
}
CHECKED = ["games", *BOX_FIELDS]


def hometown(person: dict) -> str | None:
    city, region = person.get("birthCity"), person.get("birthStateProvince")
    country = person.get("birthCountry")
    place = region if country == "USA" else country
    return ", ".join(x for x in (city, place) if x) or None


def _abbrev(teams: dict[int, dict], team: dict) -> str:
    return (teams.get(team.get("id"), {}).get("abbreviation") or team.get("name", "")[:10]).upper()


def sync_pitcher(db: Session, client: MlbClient, mlbam_id: int, season: int,
                 with_pitches: bool = True) -> Pitcher:
    # ---- everything from MLB first: Statcast can take minutes, and nothing should hold a
    # database write lock while it downloads (the API keeps serving during auto-sync) ----
    person = client.person(mlbam_id)
    teams = client.teams(season)
    logs = {sport: [s for s in client.game_log(mlbam_id, season, sport) if s.get("gameType", "R") == "R"]
            for sport in SPORT_LEVELS}
    logs = {sport: splits for sport, splits in logs.items() if splits}
    if not logs:
        raise ValueError(f"{person['fullName']} has no regular-season pitching in {season}")
    official = {sport: client.season_line(mlbam_id, season, sport) for sport in logs}
    statcast = client.statcast(mlbam_id, season) if with_pitches and 1 in logs else []

    pitcher = db.scalar(select(Pitcher).where(Pitcher.owner_id.is_(None),
                                              Pitcher.mlbam_id == mlbam_id))
    if pitcher is None:
        pitcher = Pitcher(owner_id=None, mlbam_id=mlbam_id, name=person["fullName"])
        db.add(pitcher)
    pitcher.name = person["fullName"]
    pitcher.throws = person.get("pitchHand", {}).get("code", "R")[:1]
    pitcher.hometown = hometown(person)
    pitcher.photo_url = HEADSHOT.format(id=mlbam_id)
    pitcher.source = SOURCE_MLB
    pitcher.in_portal = False
    pitcher.class_year = None
    db.flush()

    # ---- official game logs, every level ----
    existing = {a.game_pk: a for a in pitcher.appearances if a.game_pk}
    # manual or derived games would double count; this pitcher's data is now official only
    for a in list(pitcher.appearances):
        if a.source != BOX_OFFICIAL:
            pitcher.appearances.remove(a)
    db.flush()  # deletes first, so a replacement game can reuse the same date + opponent
    keep = set()
    for sport, splits in logs.items():
        per_day = defaultdict(int)
        for s in splits:
            per_day[(s["date"], s["opponent"]["id"])] += 1
        for s in splits:
            pk, st = s["game"]["gamePk"], s["stat"]
            opp = _abbrev(teams, s["opponent"])
            if per_day[(s["date"], s["opponent"]["id"])] > 1:  # pitched both ends of a doubleheader
                opp = f"{opp[:7]} G{s['game'].get('gameNumber', 1)}"
            app = existing.get(pk)
            if app is None:
                app = Appearance(pitcher=pitcher, game_pk=pk)
                db.add(app)
            app.game_date = date.fromisoformat(s["date"])
            app.opponent = opp
            app.level = SPORT_LEVELS[sport]
            app.is_start = st.get("gamesStarted", 0) > 0
            app.source = BOX_OFFICIAL
            app.official_pitches = st.get("numberOfPitches")
            for ours, theirs in BOX_FIELDS.items():
                setattr(app, ours, int(st.get(theirs, 0)))
            keep.add(pk)
    for a in list(pitcher.appearances):  # games MLB no longer lists, or from another season
        if a.game_pk not in keep:
            pitcher.appearances.remove(a)
    db.flush()

    # ---- bio from the latest game ----
    latest_sport, latest = max(((sp, s) for sp, ss in logs.items() for s in ss), key=lambda x: x[1]["date"])
    team = teams.get(latest["team"]["id"], {})
    pitcher.level = SPORT_LEVELS[latest_sport]
    pitcher.team = _abbrev(teams, latest["team"])
    parent = teams.get(team.get("parentOrgId"), {})
    pitcher.affiliation = parent.get("abbreviation") if latest_sport != 1 else None
    games = sum(len(ss) for ss in logs.values())
    starts = sum(s["stat"].get("gamesStarted", 0) for ss in logs.values() for s in ss)
    pitcher.role = "SP" if starts * 2 >= games else "RP"

    # ---- Statcast pitches for MLB games ----
    if statcast:
        by_game = defaultdict(list)
        for row in statcast:
            if row.get("game_pk"):
                by_game[int(row["game_pk"])].append(row)
        for app in pitcher.appearances:
            if app.game_pk in by_game:
                app.pitches.clear()
                db.flush()
                db.add_all(pitch_from_row(r, app) for r in by_game[app.game_pk] if thrown(r))

    db.flush()
    pitcher.verification = reconcile(db, client, pitcher, season, logs.keys(), official)
    pitcher.synced_at = utcnow()
    db.commit()
    return pitcher


def reconcile(db: Session, client: MlbClient, pitcher: Pitcher, season: int, sports,
              official_lines: dict | None = None) -> dict:
    """Compare what we stored with MLB's official season totals, level by level.

    official_lines ({sport id: season line}) skips fetching them when the caller already has.
    """
    levels = []
    for sport in sports:
        level = SPORT_LEVELS[sport]
        official = (official_lines[sport] if official_lines is not None
                    else client.season_line(pitcher.mlbam_id, season, sport)) or {}
        apps = [a for a in pitcher.appearances if a.level == level]
        ours = analytics.box_score_totals(apps)
        checks = []
        for field in CHECKED:
            theirs = official.get("gamesPlayed" if field == "games" else BOX_FIELDS[field])
            checks.append({"stat": field, "ours": ours[field],
                           "official": int(theirs) if theirs is not None else None})
        our_era = analytics.compute_stats({**ours, "pitches": 0}, group="traditional")["era"]
        official_era = float(official["era"]) if official.get("era", "-").replace(".", "").isdigit() else None
        checks.append({"stat": "era", "ours": our_era, "official": official_era})
        levels.append({"level": level, "ok": all(c["ours"] == c["official"] for c in checks),
                       "checks": checks})

    official_pitches = sum(a.official_pitches or 0 for a in pitcher.appearances if a.level == "MLB")
    loaded = db.scalar(select(func.count(Pitch.id)).join(Appearance).where(
        Appearance.pitcher_id == pitcher.id, Appearance.level == "MLB")) or 0
    return {
        "season": season,
        "checked_at": utcnow().isoformat(timespec="seconds"),
        "ok": all(lv["ok"] for lv in levels),
        "levels": levels,
        "pitches": {"official": official_pitches, "loaded": loaded} if official_pitches else None,
    }


def resolve(client: MlbClient, name: str) -> int:
    people = client.search(name)
    pitchers = [p for p in people if p.get("primaryPosition", {}).get("code") in ("1", "Y")]
    if len(pitchers) == 1:
        return pitchers[0]["id"]
    if not pitchers:
        raise SystemExit(f"No MLB pitcher found named {name!r}")
    lines = "\n".join(f"  --id {p['id']}  {p['fullName']} (born {p.get('birthDate', '?')})" for p in pitchers)
    raise SystemExit(f"Several pitchers match {name!r}; pick one:\n{lines}")


def main():
    from .db import SessionLocal, init_db

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="*", help="pitcher name(s), e.g. \"Tarik Skubal\"")
    ap.add_argument("--id", type=int, action="append", default=[], help="MLB player id (repeatable)")
    ap.add_argument("--season", type=int, default=date.today().year)
    ap.add_argument("--refresh", action="store_true", help="re-sync every MLB pitcher already loaded")
    ap.add_argument("--no-pitches", action="store_true", help="skip Statcast (box scores only)")
    args = ap.parse_args()

    init_db()
    client = MlbClient()
    with SessionLocal() as db:
        targets = [(i, args.season) for i in args.id]
        targets += [(resolve(client, n), args.season) for n in args.name]
        if args.refresh:
            targets += [(p.mlbam_id, (p.verification or {}).get("season", args.season))
                        for p in db.scalars(select(Pitcher).where(Pitcher.source == SOURCE_MLB))]
        if not targets:
            ap.error("give a name, --id or --refresh")
        failed = 0
        for mlbam_id, season in targets:
            try:
                p = sync_pitcher(db, client, mlbam_id, season, with_pitches=not args.no_pitches)
            except Exception as e:  # keep going; one bad player shouldn't stop a refresh
                db.rollback()
                failed += 1
                print(f"x {mlbam_id} {season}: {e}")
                continue
            v = p.verification
            pitches = v["pitches"]
            pitch_note = f", Statcast {pitches['loaded']}/{pitches['official']} pitches" if pitches else ""
            print(f"{'ok' if v['ok'] else 'MISMATCH'}  {p.name} {season}: "
                  f"{len(p.appearances)} games at {', '.join(lv['level'] for lv in v['levels'])}{pitch_note}")
            for lv in v["levels"]:
                for c in lv["checks"]:
                    if c["ours"] != c["official"]:
                        print(f"    {lv['level']} {c['stat']}: ours {c['ours']} vs official {c['official']}")
        raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
