"""Stat formulas.

Every stat is one entry in STATS. A formula receives a `totals` dict and returns a number:

  - box-score totals, summed over appearances: outs, ip, hits, runs, earned_runs, walks,
    strikeouts, home_runs, hit_by_pitch, batters_faced, games, games_started
  - pitch counters, aggregated in SQL (works the same on Postgres and SQLite): pitches, in_zone,
    swings, whiffs, called_strikes, csw, chases, zone_swings, zone_whiffs, fouls, in_play,
    first_pitches, first_pitch_strikes, located, judged, judged_in_zone, judged_out_of_zone,
    avg_velo, max_velo, avg_spin, fb_velo, avg_ivb, avg_hb, avg_extension, avg_release_height

To add a stat, append a Stat(...) to STATS; the API and the dashboard pick it up automatically.
If it needs a new pitch counter, add one line to pitch_counters() too. Set `better` to "higher" or
"lower" so the stat can be used for goals, trend arrows and insights.

Rates about outcomes divide by `judged` pitches (those with a known result), and Zone% by
`located` ones, so a bullpen with no batter, umpire or location shows "no data" rather than 0%.
"""

from dataclasses import asdict, dataclass, field
from typing import Callable, Literal

from sqlalchemy import and_, case, func, not_, select
from sqlalchemy.orm import Session

from .models import Appearance, Pitch, Pitcher

# Rulebook zone, widened by a baseball's radius: 17" plate -> +/-0.83 ft; generic 1.5-3.5 ft height.
ZONE_HALF_WIDTH = 0.83
ZONE_BOTTOM = 1.5
ZONE_TOP = 3.5
FIP_CONSTANT = 3.10  # league-dependent; ~3.1 is typical for MLB

SWING_RESULTS = ("swinging_strike", "foul", "in_play")
FASTBALLS = ("FF", "SI", "FT")
BOX_SCORE_FIELDS = ("outs", "hits", "runs", "earned_runs", "walks", "strikeouts",
                    "home_runs", "hit_by_pitch", "batters_faced")


def innings_display(outs: int) -> str:
    """Baseball notation: 20 outs -> '6.2'."""
    return f"{outs // 3}.{outs % 3}"


def rate(num: float | None, den: float | None, scale: float = 1.0) -> float | None:
    return num / den * scale if den and num is not None else None


@dataclass(frozen=True)
class Stat:
    key: str
    label: str
    group: str  # "traditional" (box score) or "pitching" (pitch-level; also used per pitch type)
    formula: Callable[[dict], float | str | None] = field(repr=False)
    digits: int = 2
    suffix: str = ""
    description: str = ""
    default: bool = False  # shown on the dashboard until the viewer customizes it
    better: Literal["higher", "lower"] | None = None  # None = no good/bad direction

    def compute(self, totals: dict):
        value = self.formula(totals)
        return round(value, self.digits) if isinstance(value, float) else value

    def definition(self) -> dict:
        d = asdict(self)
        d.pop("formula")
        return d


def _fip(t):
    return rate(13 * t["home_runs"] + 3 * (t["walks"] + t["hit_by_pitch"]) - 2 * t["strikeouts"],
                t["ip"]) + FIP_CONSTANT if t["ip"] else None


def _at_bats(t):
    # sacrifice flies/bunts aren't tracked separately, so this slightly overstates AB
    return t["batters_faced"] - t["walks"] - t["hit_by_pitch"]


H, L = "higher", "lower"

STATS: list[Stat] = [
    # --- traditional --------------------------------------------------------------------------
    Stat("era", "ERA", "traditional", lambda t: rate(t["earned_runs"], t["ip"], 9),
         description="Earned runs per 9 innings", default=True, better=L),
    Stat("fip", "FIP", "traditional", _fip, default=True, better=L,
         description="Fielding-independent pitching: ERA estimated from K, BB, HBP and HR only"),
    Stat("whip", "WHIP", "traditional", lambda t: rate(t["walks"] + t["hits"], t["ip"]),
         description="Walks + hits per inning", default=True, better=L),
    Stat("innings_pitched", "IP", "traditional", lambda t: innings_display(t["outs"]),
         description="Innings pitched", default=True),
    Stat("k_per_9", "K/9", "traditional", lambda t: rate(t["strikeouts"], t["ip"], 9), 1,
         description="Strikeouts per 9 innings", default=True, better=H),
    Stat("bb_per_9", "BB/9", "traditional", lambda t: rate(t["walks"], t["ip"], 9), 1,
         description="Walks per 9 innings", default=True, better=L),
    Stat("k_pct", "K%", "traditional", lambda t: rate(t["strikeouts"], t["batters_faced"], 100), 1,
         "%", "Strikeouts / batters faced", default=True, better=H),
    Stat("bb_pct", "BB%", "traditional", lambda t: rate(t["walks"], t["batters_faced"], 100), 1,
         "%", "Walks / batters faced", better=L),
    Stat("k_minus_bb_pct", "K-BB%", "traditional",
         lambda t: rate(t["strikeouts"] - t["walks"], t["batters_faced"], 100), 1, "%",
         "Strikeout rate minus walk rate - one of the best single skill indicators", better=H),
    Stat("k_bb", "K/BB", "traditional", lambda t: rate(t["strikeouts"], t["walks"]),
         description="Strikeouts per walk", better=H),
    Stat("h_per_9", "H/9", "traditional", lambda t: rate(t["hits"], t["ip"], 9), 1,
         description="Hits allowed per 9 innings", better=L),
    Stat("hr_per_9", "HR/9", "traditional", lambda t: rate(t["home_runs"], t["ip"], 9), 2,
         description="Home runs allowed per 9 innings", better=L),
    Stat("opp_avg", "Opp AVG", "traditional", lambda t: rate(t["hits"], _at_bats(t)), 3,
         description="Batting average against", better=L),
    Stat("babip", "BABIP", "traditional",
         lambda t: rate(t["hits"] - t["home_runs"],
                        _at_bats(t) - t["strikeouts"] - t["home_runs"]), 3,
         description="Batting average on balls in play (league average is ~.290)", better=L),
    Stat("pitches_per_ip", "P/IP", "traditional", lambda t: rate(t["pitches"], t["ip"]), 1,
         description="Pitches per inning (needs pitch-level data)", better=L),
    Stat("games", "G", "traditional", lambda t: t["games"], 0, description="Games pitched"),
    Stat("games_started", "GS", "traditional", lambda t: t["games_started"], 0,
         description="Games started"),
    Stat("strikeouts", "K", "traditional", lambda t: t["strikeouts"], 0, description="Strikeouts"),
    Stat("walks", "BB", "traditional", lambda t: t["walks"], 0, description="Walks"),
    Stat("hits", "H", "traditional", lambda t: t["hits"], 0, description="Hits allowed"),
    Stat("home_runs", "HR", "traditional", lambda t: t["home_runs"], 0,
         description="Home runs allowed"),
    Stat("batters_faced", "BF", "traditional", lambda t: t["batters_faced"], 0,
         description="Batters faced"),
    # --- pitch-level --------------------------------------------------------------------------
    Stat("fb_velo", "FB velo", "pitching", lambda t: t["fb_velo"], 1,
         description="Average fastball (4-seam / sinker) velocity, mph", default=True, better=H),
    Stat("f_strike_pct", "F-Strike%", "pitching",
         lambda t: rate(t["first_pitch_strikes"], t["first_pitches"], 100), 1, "%",
         "First-pitch strikes (anything but a ball) / batters", default=True, better=H),
    Stat("zone_pct", "Zone%", "pitching", lambda t: rate(t["in_zone"], t["located"], 100), 1, "%",
         "Pitches inside the strike zone", default=True),
    Stat("whiff_pct", "Whiff%", "pitching", lambda t: rate(t["whiffs"], t["swings"], 100), 1, "%",
         "Swinging strikes / swings", default=True, better=H),
    Stat("chase_pct", "Chase%", "pitching",
         lambda t: rate(t["chases"], t["judged_out_of_zone"], 100), 1, "%",
         "Swings at pitches outside the zone / pitches outside the zone", default=True, better=H),
    Stat("csw_pct", "CSW%", "pitching", lambda t: rate(t["csw"], t["judged"], 100), 1, "%",
         "Called + swinging strikes / pitches", default=True, better=H),
    Stat("pitches", "Pitches", "pitching", lambda t: t["pitches"], 0,
         description="Pitches thrown"),
    Stat("avg_velo", "Velo", "pitching", lambda t: t["avg_velo"], 1,
         description="Average velocity across all pitches (mph)"),
    Stat("max_velo", "Max velo", "pitching", lambda t: t["max_velo"], 1,
         description="Fastest pitch (mph)", better=H),
    Stat("avg_spin", "Spin", "pitching", lambda t: t["avg_spin"], 0,
         description="Average spin rate (rpm)"),
    # movement and release (Statcast, TrackMan, Rapsodo); most telling per pitch type
    Stat("ivb", "IVB", "pitching", lambda t: t["avg_ivb"], 1, '"',
         "Induced vertical break: inches of rise or drop from spin, gravity removed"),
    Stat("hb", "HB", "pitching", lambda t: t["avg_hb"], 1, '"',
         "Horizontal break in inches, positive = to the pitcher's right"),
    Stat("extension", "Extension", "pitching", lambda t: t["avg_extension"], 1, " ft",
         "How far in front of the rubber the ball is released", better=H),
    Stat("release_height", "Rel. height", "pitching", lambda t: t["avg_release_height"], 2, " ft",
         "Release height above the ground"),
    Stat("swing_pct", "Swing%", "pitching", lambda t: rate(t["swings"], t["judged"], 100), 1, "%",
         "Swings / pitches"),
    Stat("zone_swing_pct", "Z-Swing%", "pitching",
         lambda t: rate(t["zone_swings"], t["judged_in_zone"], 100), 1, "%",
         "Swings at pitches in the zone / pitches in the zone"),
    Stat("zone_contact_pct", "Z-Contact%", "pitching",
         lambda t: rate(t["zone_swings"] - t["zone_whiffs"], t["zone_swings"], 100), 1, "%",
         "Contact on swings at pitches in the zone", better=L),
    Stat("called_strike_pct", "Called strike%", "pitching",
         lambda t: rate(t["called_strikes"], t["judged"], 100), 1, "%", "Called strikes / pitches",
         better=H),
    Stat("swstr_pct", "SwStr%", "pitching", lambda t: rate(t["whiffs"], t["judged"], 100), 1, "%",
         "Swinging strikes / pitches", better=H),
]

STATS_BY_KEY = {s.key: s for s in STATS}


def compute_stats(totals: dict, group: str | None = None) -> dict:
    return {s.key: s.compute(totals) for s in STATS if group is None or s.group == group}


def is_better(stat: Stat, a: float, b: float) -> bool:
    """True if value a is better than value b for this stat."""
    return a > b if stat.better == "higher" else a < b


# --- totals ---------------------------------------------------------------------------------------

def box_score_totals(appearances: list[Appearance]) -> dict:
    t = {k: sum(getattr(a, k) for a in appearances) for k in BOX_SCORE_FIELDS}
    t["ip"] = t["outs"] / 3
    t["games"] = len(appearances)
    t["games_started"] = sum(a.is_start for a in appearances)
    return t


def _in_zone():
    return and_(
        func.abs(Pitch.plate_x) <= ZONE_HALF_WIDTH,
        Pitch.plate_z.between(ZONE_BOTTOM, ZONE_TOP),
    )


def _count_if(cond):
    return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)


def pitch_counters():
    in_zone = _in_zone()
    swing = Pitch.result.in_(SWING_RESULTS)
    judged = Pitch.result != "unknown"
    first_pitch = and_(Pitch.balls == 0, Pitch.strikes == 0, judged)
    return {
        "pitches": func.count(Pitch.id),
        "avg_velo": func.avg(Pitch.velocity),
        "max_velo": func.max(Pitch.velocity),
        "avg_spin": func.avg(Pitch.spin_rate),
        "avg_ivb": func.avg(Pitch.ivb),
        "avg_hb": func.avg(Pitch.hb),
        "avg_extension": func.avg(Pitch.extension),
        "avg_release_height": func.avg(Pitch.release_height),
        "fb_velo": func.avg(case((Pitch.pitch_type.in_(FASTBALLS), Pitch.velocity))),
        "in_zone": _count_if(in_zone),
        "swings": _count_if(swing),
        "whiffs": _count_if(Pitch.result == "swinging_strike"),
        "called_strikes": _count_if(Pitch.result == "called_strike"),
        "csw": _count_if(Pitch.result.in_(("called_strike", "swinging_strike"))),
        "chases": _count_if(and_(not_(in_zone), swing)),
        "zone_swings": _count_if(and_(in_zone, swing)),
        "zone_whiffs": _count_if(and_(in_zone, Pitch.result == "swinging_strike")),
        "fouls": _count_if(Pitch.result == "foul"),
        "in_play": _count_if(Pitch.result == "in_play"),
        "first_pitches": _count_if(first_pitch),
        "first_pitch_strikes": _count_if(
            and_(first_pitch, Pitch.result.not_in(("ball", "hit_by_pitch")))),
        "located": _count_if(and_(Pitch.plate_x.is_not(None), Pitch.plate_z.is_not(None))),
        "judged": _count_if(judged),
        "judged_in_zone": _count_if(and_(judged, in_zone)),
        "judged_out_of_zone": _count_if(and_(judged, not_(in_zone))),
    }


def pitch_counters_query(*filters):
    return select(*(expr.label(name) for name, expr in pitch_counters().items())).where(*filters)


def window_totals(db: Session, pitcher_id: int, appearances: list[Appearance],
                  whole_career: bool = True) -> dict:
    """Totals over `appearances`. whole_career=True skips the id filter (faster, same result)."""
    filters = [Pitch.pitcher_id == pitcher_id]
    if not whole_career:
        filters.append(Pitch.appearance_id.in_([a.id for a in appearances] or [-1]))
    row = db.execute(pitch_counters_query(*filters)).one()
    return {**box_score_totals(appearances), **row._asdict()}


def recent_window(pitcher: Pitcher) -> int:
    """How many recent outings count as 'recent form': ~a month for either role."""
    return 5 if pitcher.role == "SP" else 10


def stat_appearances(pitcher: Pitcher) -> list[Appearance]:
    """The games behind a pitcher's headline stats: those at his current level.

    A season split across levels (say AAA then MLB) is reported per level officially; adding
    them together gives an ERA that matches no official line.
    """
    apps = pitcher.appearances  # ordered by game_date
    if pitcher.level and any(a.level for a in apps):
        return [a for a in apps if a.level == pitcher.level]
    return apps


def season_and_recent(db: Session, pitcher: Pitcher) -> dict:
    """Season stats, last-N-games stats, and how many games the recent window covers.

    recent is None when there aren't enough games for the comparison to mean anything.
    """
    apps = stat_appearances(pitcher)
    n = recent_window(pitcher)
    season = compute_stats(window_totals(db, pitcher.id, apps,
                                         whole_career=len(apps) == len(pitcher.appearances)))
    recent = None
    if len(apps) >= n + 3:
        recent = compute_stats(window_totals(db, pitcher.id, apps[-n:], whole_career=False))
    return {"season": season, "recent": recent, "recent_games": n}


def arsenal(db: Session, pitcher_id: int) -> list[dict]:
    rows = db.execute(
        pitch_counters_query(Pitch.pitcher_id == pitcher_id)
        .add_columns(Pitch.pitch_type)
        .group_by(Pitch.pitch_type)
        .order_by(func.count(Pitch.id).desc())
    ).all()
    total = sum(r.pitches for r in rows)
    return [
        {
            "pitch_type": r.pitch_type,
            "usage_pct": round(rate(r.pitches, total, 100), 1),
            **compute_stats(r._asdict(), group="pitching"),
        }
        for r in rows
    ]


def velocity_trend(db: Session, pitcher_id: int) -> list[dict]:
    """Per-game average velocity and spin by pitch type."""
    rows = db.execute(
        select(
            Appearance.game_date,
            Pitch.pitch_type,
            func.avg(Pitch.velocity).label("velo"),
            func.avg(Pitch.spin_rate).label("spin"),
            func.count(Pitch.id).label("n"),
        )
        .join(Appearance, Pitch.appearance_id == Appearance.id)
        .where(Pitch.pitcher_id == pitcher_id)
        .group_by(Appearance.game_date, Pitch.pitch_type)
        .order_by(Appearance.game_date)
    ).all()
    return [
        {
            "game_date": r.game_date.isoformat(),
            "pitch_type": r.pitch_type,
            "avg_velo": round(r.velo, 1) if r.velo is not None else None,
            "avg_spin": round(r.spin) if r.spin is not None else None,
            "pitches": r.n,
        }
        for r in rows
    ]
