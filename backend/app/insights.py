"""Coach's Corner: rule-based insights that point a pitcher's trends in the right direction.

Each rule compares recent form (last N outings) to the season. A change bigger than the rule's
threshold becomes an insight with a concrete thing to work on (or to keep doing). These are
heuristics for development conversations, not a substitute for a coach or athletic trainer.

To add a rule, add an entry to TREND_RULES keyed by a stat in analytics.STATS.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .analytics import STATS_BY_KEY, arsenal, is_better, season_and_recent
from .models import Pitcher


@dataclass(frozen=True)
class TrendRule:
    threshold: float  # minimum |recent - season| worth mentioning, in the stat's units
    declining: str  # what to work on when the stat moves the wrong way
    improving: str  # what to keep doing when it moves the right way


TREND_RULES: dict[str, TrendRule] = {
    "fb_velo": TrendRule(
        0.8,
        "A sustained velocity drop is often fatigue. Review workload and recovery (sleep, "
        "throwing volume, days of rest) with your coach or athletic trainer before adding "
        "intensity, and get any arm discomfort checked. Once fresh, long toss and lower-half "
        "drive work help rebuild velo.",
        "Velocity is trending up. Keep the recovery and throwing routine that's working.",
    ),
    "bb_per_9": TrendRule(
        0.8,
        "Walks are climbing. Focus on getting ahead: in bullpens, start every hitter 1-0 and "
        "finish the at-bat in the zone, and track how many of 15 pitches hit the catcher's glove.",
        "Command is sharpening. Keep attacking hitters early in counts.",
    ),
    "f_strike_pct": TrendRule(
        4.0,
        "Fewer first-pitch strikes means more hitter's counts. Pick your most reliable strike "
        "pitch for 0-0 and aim middle-third. A strike early beats a perfect pitch late.",
        "Getting ahead more often. Strike one is the most valuable pitch in an at-bat.",
    ),
    "k_pct": TrendRule(
        3.0,
        "Strikeouts are down. In two-strike counts, throw your best swing-and-miss pitch and "
        "start it on the fastball's path before it breaks below the zone.",
        "Strikeouts are up. Your put-away approach is working.",
    ),
    "whiff_pct": TrendRule(
        3.0,
        "Hitters are missing less. Check pitch shape: if breaking-ball spin or velo dropped, "
        "revisit grip and release, and finish those pitches below the zone.",
        "Swing-and-miss is up. Your stuff is playing.",
    ),
    "csw_pct": TrendRule(
        2.5,
        "Called + swinging strikes are down, a sign of either location or stuff slipping. "
        "Compare the zone plot for recent games to the season to see which.",
        "CSW% is up. You're winning more pitches.",
    ),
    "hr_per_9": TrendRule(
        0.5,
        "More balls are leaving the yard. Middle-middle pitches get hit hardest: elevate the "
        "fastball on purpose (above the zone) and keep off-speed at the knees or below.",
        "Keeping the ball in the park. Location is doing its job.",
    ),
    "k_minus_bb_pct": TrendRule(
        4.0,
        "Your K-BB% (strikeout rate minus walk rate) is slipping. Focus on the side that "
        "dropped more: strikeouts or walks.",
        "K-BB% is up. That's the best single sign that a pitcher is getting better.",
    ),
}

MIN_PITCHES_FOR_MIX = 50
PITCH_NAMES = {"FF": "four-seam fastball", "SI": "sinker", "FT": "two-seam fastball",
               "FC": "cutter", "SL": "slider", "ST": "sweeper", "CU": "curveball",
               "KC": "knuckle curve", "CH": "changeup", "FS": "splitter"}


def _fmt(key: str, value) -> str:
    stat = STATS_BY_KEY[key]
    if value is None:
        return "—"
    s = f"{value:.{stat.digits}f}"
    if stat.digits == 3 and value < 1:
        s = s.lstrip("0")
    return s + stat.suffix


def trend_insights(windows: dict) -> list[dict]:
    season, recent, n = windows["season"], windows["recent"], windows["recent_games"]
    if recent is None:
        return []
    out = []
    for key, rule in TREND_RULES.items():
        s, r = season.get(key), recent.get(key)
        if s is None or r is None or abs(r - s) < rule.threshold:
            continue
        stat = STATS_BY_KEY[key]
        improving = is_better(stat, r, s)
        out.append({
            "kind": "improving" if improving else "declining",
            "stat_key": key,
            "title": f"{stat.label} {'up' if r > s else 'down'}: "
                     f"{_fmt(key, r)} over the last {n} games vs {_fmt(key, s)} on the season",
            "tip": rule.improving if improving else rule.declining,
            "season": s,
            "recent": r,
        })
    return out


def context_insights(season: dict) -> list[dict]:
    """Things that explain results without being a trend: luck and ERA/FIP gaps."""
    out = []
    era, fip, babip = season.get("era"), season.get("fip"), season.get("babip")
    if era is not None and fip is not None and abs(era - fip) >= 0.75:
        if era > fip:
            out.append({"kind": "info", "stat_key": "fip",
                        "title": f"ERA ({era:.2f}) is well above FIP ({fip:.2f})",
                        "tip": "The underlying skills (K, BB, HR) are better than the runs "
                               "allowed suggest. Defense and sequencing luck tend to even out, "
                               "so don't overhaul what's working."})
        else:
            out.append({"kind": "info", "stat_key": "fip",
                        "title": f"ERA ({era:.2f}) is well below FIP ({fip:.2f})",
                        "tip": "Results are ahead of the underlying numbers. Expect some "
                               "regression unless the strikeout and walk rates improve."})
    if babip is not None and season.get("games", 0) >= 5 and babip >= 0.330:
        out.append({"kind": "info", "stat_key": "babip",
                    "title": f"BABIP is {_fmt('babip', babip)} (league average is about .290)",
                    "tip": "More balls in play are falling for hits than usual, which is often "
                           "bad luck or defense. Judge progress by K% and BB% instead."})
    return out


def pitch_mix_insights(pitches: list[dict]) -> list[dict]:
    """Suggest leaning on the best pitch and refining the weakest heavily-used one."""
    qualified = [p for p in pitches if p["pitches"] >= MIN_PITCHES_FOR_MIX
                 and p["whiff_pct"] is not None and p["csw_pct"] is not None]
    if len(qualified) < 2:
        return []
    out = []
    best = max(qualified, key=lambda p: p["whiff_pct"])
    if best["usage_pct"] < 25:
        out.append({"kind": "pitch_mix", "stat_key": "whiff_pct", "pitch_type": best["pitch_type"],
                    "title": f"Your {PITCH_NAMES.get(best['pitch_type'], best['pitch_type'])} has your best whiff rate "
                             f"({best['whiff_pct']:.1f}%) but only {best['usage_pct']:.1f}% usage",
                    "tip": "Try it more in two-strike counts and against same-side hitters. "
                           "A pitch that misses bats is worth throwing more often."})
    weak = [p for p in qualified if p["usage_pct"] >= 15 and p is not best]
    if weak:
        worst = min(weak, key=lambda p: p["csw_pct"])
        if worst["csw_pct"] < 27:
            out.append({"kind": "pitch_mix", "stat_key": "csw_pct",
                        "pitch_type": worst["pitch_type"],
                        "title": f"Your {PITCH_NAMES.get(worst['pitch_type'], worst['pitch_type'])} wins the fewest pitches "
                                 f"({worst['csw_pct']:.1f}% CSW at {worst['usage_pct']:.1f}% usage)",
                        "tip": "Make it a bullpen focus: work on its location and shape, and "
                               "use it in less important counts until it's sharper."})
    return out


ORDER = {"declining": 0, "pitch_mix": 1, "info": 2, "improving": 3}


def build_insights(db: Session, pitcher: Pitcher, windows: dict | None = None) -> dict:
    windows = windows or season_and_recent(db, pitcher)
    items = (trend_insights(windows) + pitch_mix_insights(arsenal(db, pitcher.id))
             + context_insights(windows["season"]))
    items.sort(key=lambda i: ORDER[i["kind"]])
    return {"recent_games": windows["recent_games"], "has_recent": windows["recent"] is not None,
            "items": items}


def evaluate_goal(stat_key: str, target: float, windows: dict) -> dict:
    """met: season value reaches the target. on_track: not yet, but recent form is at the target
    or moving toward it. off_track: neither."""
    stat = STATS_BY_KEY[stat_key]
    season = windows["season"].get(stat_key)
    recent = (windows["recent"] or {}).get(stat_key)
    if season is None:
        status = "no_data"
    elif season == target or is_better(stat, season, target):
        status = "met"
    elif recent is not None and (recent == target or is_better(stat, recent, target)
                                 or is_better(stat, recent, season)):
        status = "on_track"
    else:
        status = "off_track"
    return {"season": season, "recent": recent, "status": status}
