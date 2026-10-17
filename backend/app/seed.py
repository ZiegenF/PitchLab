"""Generate a mock season of pitch-by-pitch data and load it through the Statcast ingester.

Games are simulated plate appearance by plate appearance, so the traditional stats (ERA, K/9...)
are consistent with the pitch data (zone%, whiff%...) instead of being random numbers.

    python -m app.seed            # reset + load the default season
    python -m app.seed --seed 7   # a different (still reproducible) season
    python -m app.seed --real     # also sync REAL_PITCHERS from MLB (needs network)

Covers every level a scout looks at: high school, college (including the transfer portal), each
minor-league level and MLB. Velocity scales with level; stuff/command are relative to the
competition, so a top high-school arm can post an ace's ERA at 89 mph.

Also creates a demo account (DEMO_EMAIL / DEMO_PASSWORD) that tracks a few league pitchers, has
goals set, and owns one private pitcher entered by hand, so every feature has data to show.
"""

import argparse
import math
import random
import shutil
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select

from .analytics import ZONE_BOTTOM, ZONE_HALF_WIDTH, ZONE_TOP
from .auth import hash_password, utcnow
from .db import Base, SessionLocal, engine, init_db
from .ingest import ingest_rows
from .models import (BOX_MANUAL, SOURCE_SIMULATED, Appearance, Goal, Pitcher, TrackedPitcher,
                     User)
from .photos import PHOTO_DIR

# Real 2024 seasons, synced from MLB with --real: an ace, a two-level rookie (AAA -> MLB) and a
# prospect who climbed four levels (A+ -> AA -> AAA -> MLB)
REAL_PITCHERS = [(669373, 2024), (694973, 2024), (695549, 2024)]  # Skubal, Skenes, Jobe

DEMO_EMAIL = "demo@pitchlab.dev"
DEMO_PASSWORD = "pitchlab-demo"  # local demo data only

TEAMS = ["NYY", "BOS", "TOR", "BAL", "TB", "CLE", "DET", "MIN", "KC", "CWS", "HOU", "SEA", "TEX",
         "LAA", "ATH", "ATL", "PHI", "NYM", "MIA", "WSH", "CHC", "MIL", "STL", "CIN", "PIT",
         "LAD", "SD", "SF", "ARI", "COL"]

AAA_TEAMS = ["SWB", "OKC", "DUR", "NAS", "ROC", "SAC", "LV", "WOR", "CLT", "IOW"]
AA_TEAMS = ["SOM", "CC", "TUL", "AKR", "ERI", "PNS", "FRI", "HBG", "MID", "BLX"]
HIGH_A_TEAMS = ["HV", "GVL", "BG", "ASH", "WIL", "JS", "EVE", "QC"]
LOW_A_TEAMS = ["RC", "FRE", "STK", "MOD", "INL", "VIS", "LE", "SJ"]
COLLEGES = ["BYU", "TCU", "TEX", "LSU", "VANDY", "ARK", "UCLA", "FSU", "ORST", "UTAH", "BAY",
            "OKST", "TTU", "KSU"]
HIGH_SCHOOLS = ["EASTVIEW", "LAKESIDE", "OAKCREST", "PINERIDGE", "WESTFIELD", "NORTHGATE",
                "RIVERBEND", "SUMMIT"]


@dataclass(frozen=True)
class Season:
    start: date
    end: date
    innings: int  # regulation game length
    sp_pitches: float  # typical starter pitch count
    sp_rest: tuple[int, ...]  # days between starts
    rp_rest: tuple[int, ...]
    opponents: list[str]


_PRO = dict(innings=9, rp_rest=(1, 2, 2, 3, 4))
_MILB = dict(start=date(2026, 4, 3), end=date(2026, 9, 20), sp_pitches=84, sp_rest=(6,), **_PRO)
SEASONS = {
    "MLB": Season(date(2026, 3, 27), date(2026, 9, 27), sp_pitches=92, sp_rest=(5, 5, 6, 6),
                  opponents=TEAMS, **_PRO),
    "AAA": Season(opponents=AAA_TEAMS, **_MILB),
    "AA": Season(opponents=AA_TEAMS, **_MILB),
    "A+": Season(opponents=HIGH_A_TEAMS, **_MILB),
    "A": Season(opponents=LOW_A_TEAMS, **_MILB),
    # college: weekend rotation, midweek bullpen games
    "NCAA": Season(date(2026, 2, 13), date(2026, 5, 30), innings=9, sp_pitches=96,
                   sp_rest=(7,), rp_rest=(2, 3, 4, 5), opponents=COLLEGES),
    # high school: 7-inning games, pitch-count rules
    "HS": Season(date(2026, 2, 20), date(2026, 5, 8), innings=7, sp_pitches=88,
                 sp_rest=(7,), rp_rest=(3, 4, 5, 7), opponents=HIGH_SCHOOLS),
}

# (target x for a RHP, target z, base whiff rate on swings)
PITCH_SHAPES = {
    "FF": (0.25, 2.95, 0.21),
    "SI": (0.45, 2.10, 0.12),
    "FC": (-0.35, 2.40, 0.22),
    "SL": (-0.60, 1.85, 0.34),
    "ST": (-0.75, 1.95, 0.36),
    "CU": (-0.30, 1.55, 0.31),
    "CH": (0.45, 1.80, 0.31),
    "FS": (0.30, 1.60, 0.37),
}


@dataclass
class Profile:
    name: str  # "First Last"
    team: str
    throws: str
    role: str
    arsenal: dict[str, tuple[float, float, float]]  # type -> (usage, velo, spin)
    command: float = 1.0  # tighter location
    stuff: float = 1.0  # more whiffs, weaker contact
    velo_trend: float = 0.0  # mph change across the season (negative = fatigue)
    hometown: str = ""
    level: str = "MLB"
    class_year: str | None = None  # NCAA: FR..GR, HS: graduation year
    affiliation: str | None = None  # MiLB parent club / HS college commitment
    in_portal: bool = False


PROFILES = [
    Profile("Marcus Hale", "NYY", "R", "SP",
            {"FF": (0.47, 97.4, 2460), "SL": (0.27, 88.6, 2640), "CH": (0.14, 89.1, 1790),
             "CU": (0.12, 81.8, 2710)}, command=0.92, stuff=1.18, velo_trend=-1.2,
            hometown="Tampa, FL"),
    Profile("Diego Ramos", "LAD", "L", "SP",
            {"SI": (0.38, 92.8, 2140), "CH": (0.26, 84.3, 1690), "SL": (0.22, 83.9, 2390),
             "FF": (0.14, 93.4, 2250)}, command=1.25, stuff=0.96,
            hometown="Santo Domingo, Dominican Republic"),
    Profile("Tyler Brooks", "ATL", "R", "SP",
            {"FF": (0.44, 94.1, 2310), "CU": (0.24, 78.9, 2860), "FC": (0.18, 89.7, 2480),
             "CH": (0.14, 86.2, 1850)}, command=1.05, stuff=1.02, velo_trend=0.6,
            hometown="Macon, GA"),
    Profile("Kenji Watanabe", "SEA", "R", "SP",
            {"FF": (0.40, 95.2, 2350), "FS": (0.28, 87.4, 1290), "ST": (0.20, 84.6, 2610),
             "CU": (0.12, 76.8, 2550)}, command=1.10, stuff=1.12,
            hometown="Osaka, Japan"),
    Profile("Cole Mercer", "HOU", "R", "RP",
            {"FF": (0.62, 99.1, 2520), "SL": (0.38, 89.3, 2790)}, command=0.85, stuff=1.30,
            hometown="San Antonio, TX"),
    Profile("Andre Wallace", "CHC", "L", "RP",
            {"SI": (0.50, 95.3, 2190), "SL": (0.34, 86.1, 2560), "CH": (0.16, 87.0, 1760)},
            command=1.0, stuff=1.08, velo_trend=-0.8, hometown="Chicago, IL"),

    # ---- minor leagues ----
    Profile("Luis Navarro", "SWB", "R", "SP",
            {"FF": (0.50, 95.6, 2390), "SL": (0.30, 86.9, 2580), "CH": (0.20, 87.8, 1750)},
            command=1.0, stuff=1.06, hometown="Valencia, Venezuela", level="AAA", affiliation="NYY"),
    Profile("Brett Kowalski", "OKC", "L", "RP",
            {"SI": (0.58, 94.1, 2210), "SL": (0.42, 84.7, 2490)}, command=0.9, stuff=1.05,
            hometown="Toledo, OH", level="AAA", affiliation="LAD"),
    Profile("Isaiah Grant", "SOM", "R", "SP",
            {"FF": (0.52, 94.8, 2440), "CU": (0.28, 79.5, 2780), "CH": (0.20, 86.0, 1810)},
            command=0.88, stuff=1.10, velo_trend=0.9, hometown="Atlanta, GA", level="AA",
            affiliation="NYY"),
    Profile("Mateo Silva", "CC", "L", "SP",
            {"FF": (0.45, 92.3, 2280), "CH": (0.32, 83.1, 1660), "SL": (0.23, 82.0, 2370)},
            command=1.15, stuff=0.98, hometown="Hermosillo, Mexico", level="AA", affiliation="HOU"),
    Profile("Ryan Okafor", "HV", "R", "SP",
            {"FF": (0.55, 95.9, 2410), "SL": (0.35, 86.2, 2650), "CH": (0.10, 87.4, 1830)},
            command=0.80, stuff=1.15, hometown="Houston, TX", level="A+", affiliation="NYY"),
    Profile("Camden Price", "RC", "L", "SP",
            {"FF": (0.50, 91.4, 2300), "CU": (0.28, 76.5, 2690), "CH": (0.22, 82.9, 1700)},
            command=1.05, stuff=1.0, hometown="Boise, ID", level="A", affiliation="LAD"),

    # ---- college ----
    Profile("Ziegen Farley", "BYU", "R", "SP",
            {"FF": (0.46, 92.6, 2380), "SL": (0.26, 83.4, 2550), "CH": (0.16, 84.8, 1720),
             "CU": (0.12, 76.9, 2610)}, command=1.12, stuff=1.14, velo_trend=0.5,
            hometown="San Antonio, TX", level="NCAA", class_year="SR"),
    Profile("Tanner Hughes", "LSU", "R", "SP",
            {"FF": (0.48, 94.2, 2420), "ST": (0.32, 82.8, 2700), "CH": (0.20, 85.6, 1790)},
            command=1.0, stuff=1.12, hometown="Baton Rouge, LA", level="NCAA", class_year="JR"),
    Profile("Eli Martinez", "TCU", "L", "RP",
            {"FF": (0.55, 91.0, 2330), "SL": (0.30, 80.5, 2460), "CH": (0.15, 82.0, 1680)},
            command=0.95, stuff=1.06, hometown="El Paso, TX", level="NCAA", class_year="SO",
            in_portal=True),
    Profile("Nate Sorensen", "UTAH", "R", "SP",
            {"SI": (0.48, 90.4, 2150), "SL": (0.30, 81.5, 2420), "CH": (0.22, 83.2, 1700)},
            command=1.18, stuff=0.98, hometown="Provo, UT", level="NCAA", class_year="JR",
            in_portal=True),
    Profile("Jace Whitfield", "ARK", "R", "RP",
            {"FF": (0.64, 95.1, 2480), "SL": (0.36, 85.0, 2710)}, command=0.82, stuff=1.20,
            hometown="Fort Smith, AR", level="NCAA", class_year="SR"),

    # ---- high school ----
    Profile("Malik Johnson", "OAKCREST", "R", "SP",
            {"FF": (0.58, 90.8, 2320), "SL": (0.27, 79.4, 2490), "CH": (0.15, 81.0, 1690)},
            command=0.90, stuff=1.20, hometown="Nashville, TN", level="HS", class_year="2027",
            affiliation="Vanderbilt"),
    Profile("Brody Collins", "LAKESIDE", "R", "SP",
            {"FF": (0.55, 88.9, 2250), "CU": (0.28, 72.5, 2560), "CH": (0.17, 79.8, 1640)},
            command=1.05, stuff=1.12, hometown="Austin, TX", level="HS", class_year="2026",
            affiliation="Texas"),
    Profile("Sam Delgado", "RIVERBEND", "L", "SP",
            {"FF": (0.60, 84.6, 2180), "CU": (0.25, 70.2, 2410), "CH": (0.15, 76.4, 1590)},
            command=0.85, stuff=1.0, hometown="Albuquerque, NM", level="HS", class_year="2028"),
]


class GameSim:
    def __init__(self, rng: random.Random, p: Profile, gdate: date, opp: str, home: bool,
                 season_progress: float):
        self.rng, self.p = rng, p
        self.gdate, self.opp, self.home = gdate, opp, home
        # game-day velo: seasonal trend + day-to-day noise
        self.velo_offset = p.velo_trend * season_progress + rng.gauss(0, 0.45)
        self.rows: list[dict] = []
        self.score = 0
        self.pitch_count = 0

    def run(self) -> list[dict]:
        rng, season = self.rng, SEASONS[self.p.level]
        last = season.innings
        if self.p.role == "SP":
            budget, max_runs, inning = rng.gauss(season.sp_pitches, 10), 6, 1
        else:
            budget, max_runs = rng.uniform(14, 30), 4
            inning = rng.choice([last - 2, last - 1, last - 1, last, last, last])
        done = False
        while not done and inning <= last:
            outs, bases = 0, [False, False, False]
            while outs < 3:
                outs, bases = self.plate_appearance(inning, outs, bases)
                if self.pitch_count >= budget or self.score >= max_runs:
                    done = True
                    break
            if self.p.role == "RP" and outs >= 3 and (self.pitch_count > 18 or rng.random() < 0.8):
                done = True
            inning += 1
        return self.rows

    def plate_appearance(self, inning, outs, bases):
        rng, p = self.rng, self.p
        balls = strikes = 0
        types, weights = zip(*((t, v[0]) for t, v in p.arsenal.items()))
        while True:
            pt = rng.choices(types, weights)[0]
            _, velo, spin = p.arsenal[pt]
            tx, tz, whiff = PITCH_SHAPES[pt]
            if p.throws == "L":
                tx = -tx
            sd = 0.72 / p.command
            x, z = rng.gauss(tx, sd), rng.gauss(tz, sd * 0.95)
            in_zone = abs(x) <= ZONE_HALF_WIDTH and ZONE_BOTTOM <= z <= ZONE_TOP
            fatigue = -0.012 * max(0, self.pitch_count - 60)
            row = {
                "player_name": f"{p.name.split(' ', 1)[1]}, {p.name.split(' ', 1)[0]}",
                "game_date": self.gdate.isoformat(),
                "pitch_type": pt,
                "release_speed": round(rng.gauss(velo + self.velo_offset + fatigue, 0.8), 1),
                "release_spin_rate": round(rng.gauss(spin, 55)),
                "plate_x": round(x, 2), "plate_z": round(z, 2),
                "inning": inning, "balls": balls, "strikes": strikes,
                "inning_topbot": "Top" if self.home else "Bot",
                "home_team": p.team if self.home else self.opp,
                "away_team": self.opp if self.home else p.team,
                "p_throws": p.throws,
                "bat_score": self.score, "post_bat_score": self.score, "events": "",
            }
            self.rows.append(row)
            self.pitch_count += 1

            swing_p = (0.66 if in_zone else 0.29 * (0.85 + 0.15 * p.stuff)) + 0.10 * (strikes == 2)
            if rng.random() < swing_p:
                whiff_p = min(0.7, whiff * p.stuff * (1.0 if in_zone else 1.3))
                if rng.random() < whiff_p:
                    row["description"] = "swinging_strike"
                    strikes += 1
                elif rng.random() < 0.52:
                    row["description"] = "foul"
                    strikes = min(2, strikes + 1)
                else:
                    row["description"] = "hit_into_play"
                    return self.ball_in_play(row, in_zone, x, z, outs, bases)
            else:
                called_strike = rng.random() < (0.88 if in_zone else 0.07)
                if called_strike:
                    row["description"] = "called_strike"
                    strikes += 1
                elif not in_zone and abs(x) > 1.6 and rng.random() < 0.08:
                    row["description"] = "hit_by_pitch"
                    row["events"] = "hit_by_pitch"
                    return outs, self.force_advance(row, bases)
                else:
                    row["description"] = "ball"
                    balls += 1

            if strikes == 3:
                row["events"] = "strikeout"
                return outs + 1, bases
            if balls == 4:
                row["events"] = "walk"
                return outs, self.force_advance(row, bases)

    def ball_in_play(self, row, in_zone, x, z, outs, bases):
        rng = self.rng
        # middle-middle gets hit harder
        meatball = in_zone and abs(x) < 0.4 and 2.1 < z < 2.9
        damage = (1.45 if meatball else 1.0 if in_zone else 0.7) / self.p.stuff
        r = rng.random()
        hr, triple, double, single = 0.048 * damage, 0.007, 0.075 * damage, 0.235 * damage
        b1, b2, b3 = bases
        if r < hr:
            row["events"] = "home_run"
            self.add_runs(row, 1 + sum(bases))
            return outs, [False, False, False]
        r -= hr
        if r < triple:
            row["events"] = "triple"
            self.add_runs(row, sum(bases))
            return outs, [False, False, True]
        r -= triple
        if r < double:
            row["events"] = "double"
            self.add_runs(row, b2 + b3)
            return outs, [False, True, b1]
        r -= double
        if r < single:
            row["events"] = "single"
            self.add_runs(row, b2 + b3)
            return outs, [True, b1, False]
        # an out
        if b1 and outs < 2 and rng.random() < 0.13:
            row["events"] = "grounded_into_double_play"
            return outs + 2, [False, b2, b3]
        if b3 and outs < 2 and rng.random() < 0.35:
            row["events"] = "sac_fly"
            self.add_runs(row, 1)
            return outs + 1, [b1, b2, False]
        row["events"] = "field_out"
        return outs + 1, bases

    def force_advance(self, row, bases):
        b1, b2, b3 = bases
        if b1 and b2 and b3:
            self.add_runs(row, 1)
        # batter takes 1st; runners move up only when forced
        return [True, b1 or b2, b3 or (b1 and b2)]

    def add_runs(self, row, n):
        self.score += n
        row["post_bat_score"] = self.score


def generate_season(seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    for p in PROFILES:
        season = SEASONS[p.level]
        span = (season.end - season.start).days
        rest = season.sp_rest if p.role == "SP" else season.rp_rest
        d = season.start + timedelta(days=rng.randint(0, 4))
        while d <= season.end:
            opp = rng.choice([t for t in season.opponents if t != p.team])
            sim = GameSim(rng, p, d, opp, home=rng.random() < 0.5,
                          season_progress=math.sin(math.pi / 2 * (d - season.start).days / span))
            rows.extend(sim.run())
            d += timedelta(days=rng.choice(rest))
    return rows


def seed_demo_account(db, rng: random.Random) -> None:
    now = utcnow()
    user = User(email=DEMO_EMAIL, display_name="Demo Coach", created_at=now,
                password_hash=hash_password(DEMO_PASSWORD))
    db.add(user)
    db.flush()

    # a private pitcher entered game by game, with walks improving over the season
    mine = Pitcher(owner_id=user.id, name="Jordan Reyes", team="WILDCATS", throws="R", role="SP",
                   hometown="Phoenix, AZ", level="HS", class_year="2027", source=SOURCE_SIMULATED)
    db.add(mine)
    db.flush()
    d = date(2026, 3, 7)
    for i in range(14):
        outs = rng.choice([12, 15, 15, 18, 18, 21])
        walks = max(0, round(rng.gauss(4.8 - i * 0.3, 0.8)))
        hits = max(0, round(rng.gauss(outs / 3.4, 1.5)))
        hrs = int(rng.random() < 0.3)
        runs = max(hrs, round(rng.gauss((hits + walks) * 0.35, 1)))
        db.add(Appearance(
            pitcher_id=mine.id, game_date=d, opponent=rng.choice(["EAGLES", "HAWKS", "BEARS", "COUGARS"]),
            is_start=True, outs=outs, hits=hits, runs=runs, earned_runs=max(0, runs - int(rng.random() < 0.3)),
            walks=walks, strikeouts=max(0, round(rng.gauss(outs / 3 * 1.1, 1.5))), home_runs=hrs,
            hit_by_pitch=int(rng.random() < 0.25), batters_faced=outs + hits + walks + 1,
            source=BOX_MANUAL, level="HS"))
        d += timedelta(days=7)

    league = {p.name: p for p in db.query(Pitcher).filter(Pitcher.owner_id.is_(None))}
    tracked = [mine, league["Marcus Hale"], league["Kenji Watanabe"], league["Diego Ramos"],
               league["Ziegen Farley"], league["Malik Johnson"]]
    for p in tracked:
        db.add(TrackedPitcher(user_id=user.id, pitcher_id=p.id, created_at=now))
    for pitcher, stat, target in [(mine, "bb_per_9", 3.5), (mine, "k_per_9", 9.0),
                                  (league["Marcus Hale"], "fb_velo", 97.0),
                                  (league["Kenji Watanabe"], "whiff_pct", 36.0)]:
        db.add(Goal(user_id=user.id, pitcher_id=pitcher.id, stat_key=stat, target=target,
                    created_at=now))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--real", action="store_true", help="also sync REAL_PITCHERS from MLB")
    args = ap.parse_args()
    Base.metadata.drop_all(engine)
    init_db()
    shutil.rmtree(PHOTO_DIR, ignore_errors=True)  # photos belonged to the rows just dropped
    rows = generate_season(args.seed)
    with SessionLocal() as db:
        result = ingest_rows(db, rows, role_hint={p.name: p.role for p in PROFILES},
                             source=SOURCE_SIMULATED)
        result.pop("pitcher_ids")
        for p in PROFILES:
            db.query(Pitcher).filter_by(name=p.name, owner_id=None).update({
                "hometown": p.hometown, "level": p.level, "class_year": p.class_year,
                "affiliation": p.affiliation, "in_portal": p.in_portal})
            pid = db.scalar(select(Pitcher.id).filter_by(name=p.name, owner_id=None))
            db.query(Appearance).filter_by(pitcher_id=pid).update({"level": p.level})
        seed_demo_account(db, random.Random(args.seed))
        db.commit()
    print(f"Seeded {result}")
    if args.real:
        from .mlb import MlbClient
        from .sync_mlb import sync_pitcher
        client = MlbClient()
        with SessionLocal() as db:
            for mlbam_id, season in REAL_PITCHERS:
                p = sync_pitcher(db, client, mlbam_id, season)
                print(f"{'ok' if p.verification['ok'] else 'MISMATCH'}  {p.name} {season} (real)")
    print(f"Demo account: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
