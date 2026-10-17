"""Real-data accuracy: sync Tarik Skubal's 2024 season from recorded MLB responses and check
every number against his official line (18-4, 2.39 ERA, 192.0 IP, 228 K, 35 BB, 2,866 pitches).

The fixtures are real Stats API / Baseball Savant responses (trimmed to the columns we use), so
this runs offline. Re-record with tests/fixtures/record_mlb.py.
"""

import csv
import gzip
import json
from pathlib import Path

from sqlalchemy import select

from app import db as db_module
from app.models import BOX_DERIVED, BOX_OFFICIAL, Appearance, Pitch, Pitcher
from app.sync_mlb import reconcile, sync_pitcher

from .test_api import client, row, signup, upload  # noqa: F401  (client is a fixture)

FIXTURES = Path(__file__).parent / "fixtures" / "skubal_2024"
SKUBAL = 669373


class RecordedMlb:
    """Stands in for MlbClient, serving recorded responses."""

    def __init__(self, folder: Path = FIXTURES):
        self.data = json.loads((folder / "stats_api.json").read_text(encoding="utf-8"))
        with gzip.open(folder / "statcast.csv.gz", "rt", encoding="utf-8", newline="") as f:
            self.rows = list(csv.DictReader(f))

    def person(self, mlbam_id):
        return self.data["person"]

    def teams(self, season):
        return {t["id"]: t for t in self.data["teams"]}

    def game_log(self, mlbam_id, season, sport_id):
        return self.data["game_log"] if sport_id == 1 else []

    def season_line(self, mlbam_id, season, sport_id):
        return self.data["season_line"] if sport_id == 1 else None

    def statcast(self, mlbam_id, season):
        return self.rows


def sync(**kw) -> int:
    with db_module.SessionLocal() as db:
        return sync_pitcher(db, RecordedMlb(), SKUBAL, 2024, **kw).id


def test_synced_season_matches_official_line(client):
    pid = sync()
    body = client.get(f"/api/pitchers/{pid}").json()
    p, stats = body["pitcher"], body["stats"]
    assert (p["name"], p["team"], p["level"], p["throws"], p["role"]) == \
        ("Tarik Skubal", "DET", "MLB", "L", "SP")
    assert p["hometown"] == "Hayward, CA" and p["source"] == "mlb" and p["mlbam_id"] == SKUBAL
    assert p["photo_url"].startswith("https://img.mlbstatic.com/")

    assert stats["games"] == 31 and stats["innings_pitched"] == "192.0"
    assert stats["era"] == 2.39 and stats["whip"] == 0.92
    assert stats["k_per_9"] == 10.7 and stats["bb_per_9"] == 1.6

    v = p["verification"]
    assert v["ok"] and v["season"] == 2024
    checks = {c["stat"]: (c["ours"], c["official"]) for c in v["levels"][0]["checks"]}
    assert checks["strikeouts"] == (228, 228) and checks["earned_runs"] == (51, 51)
    assert checks["era"] == (2.39, 2.39)
    # pitch-clock violations are in Statcast but weren't thrown; the official count excludes them
    assert v["pitches"] == {"official": 2866, "loaded": 2866}


def test_box_scores_are_official_not_derived(client):
    pid = sync()
    games = client.get(f"/api/pitchers/{pid}/games").json()
    assert {g["source"] for g in games} == {BOX_OFFICIAL}
    assert all(g["pitches"] == g["official_pitches"] for g in games)
    opening_day = next(g for g in games if g["game_date"] == "2024-03-28")
    assert (opening_day["opponent"], opening_day["innings_pitched"], opening_day["strikeouts"]) == \
        ("CWS", "6.0", 6)


def test_headline_stats_use_the_current_level_only(client):
    """Paul Skenes 2024: AAA then MLB. Mixing them gives a 1.80 ERA, which matches neither
    official line; the card should show his MLB numbers."""
    with db_module.SessionLocal() as db:
        pid = sync_pitcher(db, RecordedMlb(), SKUBAL, 2024, with_pitches=False).id
        pitcher = db.get(Pitcher, pid)
        minors = Appearance(pitcher=pitcher, game_date=pitcher.appearances[0].game_date,
                            opponent="IOW", level="AAA", outs=15, earned_runs=5, source=BOX_OFFICIAL)
        db.add(minors)
        db.commit()
    listed = next(p for p in client.get("/api/pitchers").json() if p["id"] == pid)
    assert listed["era"] == 2.39 and listed["games"] == 31
    assert client.get(f"/api/pitchers/{pid}").json()["stats"]["era"] == 2.39


def test_resync_is_idempotent(client):
    pid = sync()
    assert sync() == pid
    with db_module.SessionLocal() as db:
        assert db.query(Appearance).filter_by(pitcher_id=pid).count() == 31
        assert db.query(Pitch).filter_by(pitcher_id=pid).count() == 2866


def test_reconcile_flags_a_mismatch(client):
    pid = sync(with_pitches=False)
    with db_module.SessionLocal() as db:
        pitcher = db.get(Pitcher, pid)
        pitcher.appearances[0].strikeouts -= 1  # a bad row slips in
        db.flush()
        v = reconcile(db, RecordedMlb(), pitcher, 2024, [1])
    assert not v["ok"]
    bad = [c for c in v["levels"][0]["checks"] if c["ours"] != c["official"]]
    assert [(c["stat"], c["ours"], c["official"]) for c in bad] == [("strikeouts", 227, 228)]
    assert v["pitches"] == {"official": 2866, "loaded": 0}  # Statcast skipped: coverage shows it


def test_sync_replaces_derived_games(client):
    """A league pitcher first loaded from a CSV becomes official-only once synced."""
    rows = [r for r in RecordedMlb().rows if r["game_date"] == "2024-03-28"]
    with db_module.SessionLocal() as db:
        from app.ingest import ingest_rows
        pid = ingest_rows(db, rows)["pitcher_ids"][0]
        assert db.get(Pitcher, pid).appearances[0].source == BOX_DERIVED
    assert sync() == pid  # matched by MLB id, not duplicated
    with db_module.SessionLocal() as db:
        sources = set(db.scalars(select(Appearance.source).where(Appearance.pitcher_id == pid)))
    assert sources == {BOX_OFFICIAL}


# --- provenance for non-synced data ---------------------------------------------------------------

def test_sources_are_recorded(client):
    signup(client)
    manual = client.post("/api/pitchers", json={"name": "By Hand"}).json()
    assert manual["source"] == "manual"
    client.post(f"/api/pitchers/{manual['id']}/games",
                json={"game_date": "2026-04-01", "innings_pitched": "5.0"})
    assert client.get(f"/api/pitchers/{manual['id']}/games").json()[0]["source"] == "manual"

    upload(client, [row(player_name="Csv, Carl")])
    csv_p = next(p for p in client.get("/api/pitchers").json() if p["name"] == "Carl Csv")
    assert csv_p["source"] == "csv"
    assert client.get(f"/api/pitchers/{csv_p['id']}/games").json()[0]["source"] == BOX_DERIVED


def test_csv_matches_pitchers_by_mlb_id_not_name(client):
    signup(client)
    r = upload(client, [row(player_name="Garcia, Luis", pitcher=472610),
                        row(player_name="Garcia, Luis", pitcher=677651, game_date="2026-05-02")])
    assert r.json()["pitchers"] == 2
    upload(client, [row(player_name="Garcia, Luis", pitcher=472610, game_date="2026-05-09")])
    games = {p["name"]: p["games"] for p in client.get("/api/pitchers").json()}
    # names are unique per account, so the second Luis is labeled with his id
    assert games == {"Luis Garcia": 2, "Luis Garcia (677651)": 1}


def test_pitch_clock_violations_are_not_pitches(client):
    signup(client)
    r = upload(client, [row(), row(description="automatic_ball", pitch_type="")])
    assert r.json()["pitches"] == 1
