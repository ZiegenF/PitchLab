import csv
import io
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite://"  # in-memory, set before the app imports the engine
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app.analytics import STATS, box_score_totals, compute_stats, innings_display
from app.ingest import ingest_rows
from app.insights import evaluate_goal, pitch_mix_insights, trend_insights
from app.models import Appearance, Pitcher, User

# one shared in-memory connection so every session sees the same tables
db_module.engine = db_module.create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
db_module.SessionLocal.configure(bind=db_module.engine)

from app.main import app  # noqa: E402


def row(**kw):
    base = {
        "player_name": "Doe, Jane", "game_date": "2026-05-01", "pitch_type": "FF",
        "release_speed": "95.0", "release_spin_rate": "2400", "plate_x": "0.0", "plate_z": "2.5",
        "description": "called_strike", "events": "", "inning": "1", "balls": "0", "strikes": "0",
        "inning_topbot": "Top", "home_team": "NYY", "away_team": "BOS", "p_throws": "R",
        "bat_score": "0", "post_bat_score": "0",
    }
    base.update({k: str(v) for k, v in kw.items()})
    return base


def to_csv(rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


def upload(client, rows):
    return client.post("/api/ingest/statcast",
                       files={"file": ("sc.csv", to_csv(rows), "text/csv")})


def traditional(apps):
    return compute_stats({**box_score_totals(apps), "pitches": 0}, group="traditional")


def signup(client, email="coach@example.com", password="correct-horse", name="Coach"):
    r = client.post("/api/auth/signup",
                    json={"email": email, "password": password, "display_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def make_public_pitcher(rows=None) -> int:
    """League data, loaded the way the seed script does it."""
    with db_module.SessionLocal() as db:
        result = ingest_rows(db, rows or [row(player_name="League, Larry")])
    return result["pitcher_ids"][0]


@pytest.fixture
def client():
    db_module.Base.metadata.drop_all(db_module.engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def anon():
    """A second client with its own cookie jar (no session)."""
    with TestClient(app) as c:
        yield c


# --- stat formulas --------------------------------------------------------------------------------

def test_innings_display():
    assert innings_display(20) == "6.2"
    assert innings_display(0) == "0.0"


def test_traditional_stats_formulas():
    apps = [Appearance(outs=27, hits=6, runs=3, earned_runs=3, walks=3, strikeouts=9,
                       home_runs=1, hit_by_pitch=0, batters_faced=36, is_start=True)]
    s = traditional(apps)
    assert s["era"] == 3.0
    assert s["whip"] == 1.0
    assert s["k_per_9"] == 9.0
    assert s["k_bb"] == 3.0
    assert s["fip"] == round((13 + 9 - 18) / 9 + 3.10, 2)
    assert s["opp_avg"] == round(6 / 33, 3)
    assert s["babip"] == round(5 / (33 - 9 - 1), 3)
    assert s["k_minus_bb_pct"] == round(6 / 36 * 100, 1)


def test_empty_stats_do_not_divide_by_zero():
    s = traditional([])
    assert s["era"] is None and s["fip"] is None and s["pitches_per_ip"] is None


def test_stat_registry_is_served_and_complete(client):
    defs = client.get("/api/stats").json()
    assert [d["key"] for d in defs] == [s.key for s in STATS]
    assert len({d["key"] for d in defs}) == len(defs)  # keys are unique
    assert all(d["group"] in ("traditional", "pitching") for d in defs)
    assert all(d["better"] in ("higher", "lower", None) for d in defs)


# --- ingest ---------------------------------------------------------------------------------------

def test_ingest_statcast_csv_derives_box_score(client):
    signup(client)
    rows = [
        # K on 3 pitches (one out of zone, chased)
        row(description="called_strike"),
        row(description="swinging_strike", strikes=1, plate_x=1.5, pitch_type="SL",
            release_speed=86),
        row(description="swinging_strike", strikes=2, events="strikeout"),
        # solo HR on the first pitch of the at-bat
        row(description="hit_into_play", events="home_run", bat_score=0, post_bat_score=1),
        # walk on a 3-0 ball
        row(description="ball", balls=3, plate_z=4.5, events="walk"),
        # GIDP, first pitch
        row(description="hit_into_play", events="grounded_into_double_play"),
    ]
    r = upload(client, rows)
    assert r.status_code == 200, r.text
    assert r.json() == {"pitchers": 1, "appearances": 1, "pitches": 6, "skipped_rows": 0}

    pitcher = client.get("/api/pitchers").json()[0]
    assert pitcher["name"] == "Jane Doe" and pitcher["team"] == "NYY"
    assert pitcher["is_mine"] and pitcher["is_tracked"] and not pitcher["is_public"]

    g = client.get(f"/api/pitchers/{pitcher['id']}/games").json()[0]
    assert g["opponent"] == "BOS" and g["is_start"]
    assert (g["innings_pitched"], g["strikeouts"], g["walks"], g["hits"], g["home_runs"],
            g["runs"], g["batters_faced"]) == ("1.0", 1, 1, 1, 1, 1, 4)

    p = client.get(f"/api/pitchers/{pitcher['id']}").json()["stats"]
    assert p["pitches"] == 6
    assert p["innings_pitched"] == "1.0" and p["era"] == 9.0
    assert p["zone_pct"] == round(4 / 6 * 100, 1)  # SL at x=1.5 and ball at z=4.5 are outside
    assert p["whiff_pct"] == round(2 / 4 * 100, 1)  # 2 whiffs / 4 swings
    assert p["chase_pct"] == 50.0  # 1 swing on 2 out-of-zone pitches
    assert p["pitches_per_ip"] == 6.0
    assert p["fb_velo"] == 95.0  # the SL at 86 is excluded
    assert p["f_strike_pct"] == round(3 / 3 * 100, 1)  # 0-0 pitches: called strike, HR, GIDP

    arsenal = client.get(f"/api/pitchers/{pitcher['id']}/arsenal").json()
    assert [a["pitch_type"] for a in arsenal] == ["FF", "SL"]
    assert arsenal[1]["avg_velo"] == 86.0
    assert sum(a["usage_pct"] for a in arsenal) == 100.0


def test_ingest_requires_sign_in(client):
    assert upload(client, [row()]).status_code == 401


def test_reingest_same_game_replaces_it(client):
    signup(client)
    upload(client, [row(), row()])
    upload(client, [row(), row()])
    pid = client.get("/api/pitchers").json()[0]["id"]
    assert len(client.get(f"/api/pitchers/{pid}/pitches").json()) == 2


def test_two_users_with_same_pitcher_name_stay_separate(client, anon):
    signup(client, "a@example.com")
    signup(anon, "b@example.com")
    upload(client, [row()])
    upload(anon, [row(), row()])
    mine = client.get("/api/pitchers").json()
    theirs = anon.get("/api/pitchers").json()
    assert len(mine) == len(theirs) == 1 and mine[0]["id"] != theirs[0]["id"]


def test_pitch_filter_and_404(client):
    signup(client)
    upload(client, [row(), row(pitch_type="CH")])
    pid = client.get("/api/pitchers").json()[0]["id"]
    ch = client.get(f"/api/pitchers/{pid}/pitches", params={"pitch_type": "CH"}).json()
    assert len(ch) == 1 and ch[0]["pitch_type"] == "CH"
    assert client.get("/api/pitchers/999").status_code == 404


def test_seed_generator_is_consistent():
    from app.seed import generate_season
    rows = generate_season(seed=1)
    assert rows == generate_season(seed=1)  # reproducible
    assert {r["description"] for r in rows} <= {
        "ball", "called_strike", "swinging_strike", "foul", "hit_into_play", "hit_by_pitch"}


# --- accounts -------------------------------------------------------------------------------------

def test_signup_login_logout(client, anon):
    user = signup(client, "Coach@Example.com")
    assert user["email"] == "coach@example.com"  # normalized
    assert client.get("/api/auth/me").json()["id"] == user["id"]

    with db_module.SessionLocal() as db:
        stored = db.scalar(select(User)).password_hash
    assert "correct-horse" not in stored and stored.startswith("scrypt$")

    assert anon.post("/api/auth/login", json={"email": "coach@example.com",
                                              "password": "wrong-password"}).status_code == 401
    assert anon.post("/api/auth/login", json={"email": "nobody@example.com",
                                              "password": "whatever1"}).status_code == 401
    r = anon.post("/api/auth/login", json={"email": "COACH@example.com",
                                           "password": "correct-horse"})
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json() is None
    assert anon.get("/api/auth/me").json()["id"] == user["id"]  # other session unaffected


def test_signup_validation(client):
    signup(client)
    assert client.post("/api/auth/signup", json={
        "email": "coach@example.com", "password": "another-pw", "display_name": "X"
    }).status_code == 409
    assert client.post("/api/auth/signup", json={
        "email": "new@example.com", "password": "short", "display_name": "X"
    }).status_code == 422
    assert client.post("/api/auth/signup", json={
        "email": "not-an-email", "password": "long-enough", "display_name": "X"
    }).status_code == 422


def test_private_pitchers_are_invisible_to_others(client, anon):
    signup(client)
    pid = client.post("/api/pitchers", json={"name": "Me"}).json()["id"]
    assert client.get(f"/api/pitchers/{pid}").status_code == 200

    assert anon.get(f"/api/pitchers/{pid}").status_code == 404
    assert all(p["id"] != pid for p in anon.get("/api/pitchers").json())
    signup(anon, "other@example.com")
    assert anon.get(f"/api/pitchers/{pid}").status_code == 404
    assert anon.patch(f"/api/pitchers/{pid}", json={"name": "Hacked"}).status_code == 404
    assert anon.delete(f"/api/pitchers/{pid}").status_code == 404
    assert anon.put(f"/api/me/tracked/{pid}").status_code == 404


def test_league_pitchers_are_read_only(client):
    pid = make_public_pitcher()
    assert client.get(f"/api/pitchers/{pid}").json()["pitcher"]["is_public"]
    assert client.patch(f"/api/pitchers/{pid}", json={"name": "X"}).status_code == 403
    signup(client)
    assert client.patch(f"/api/pitchers/{pid}", json={"name": "X"}).status_code == 403
    assert client.delete(f"/api/pitchers/{pid}").status_code == 403
    assert client.post(f"/api/pitchers/{pid}/games", json={
        "game_date": "2026-04-10", "innings_pitched": "1"}).status_code == 403


def test_create_pitcher_requires_sign_in_and_is_auto_tracked(client):
    assert client.post("/api/pitchers", json={"name": "Me"}).status_code == 401
    signup(client)
    r = client.post("/api/pitchers", json={"name": "Me", "throws": "L"})
    assert r.status_code == 201 and r.json()["is_tracked"] and r.json()["is_mine"]
    assert client.post("/api/pitchers", json={"name": "Me"}).status_code == 409
    players = client.get("/api/me/dashboard").json()["players"]
    assert [p["pitcher"]["name"] for p in players] == ["Me"]


def test_delete_account_removes_everything_it_owns(client):
    signup(client)
    pid = client.post("/api/pitchers", json={"name": "Me"}).json()["id"]
    client.post(f"/api/pitchers/{pid}/games",
                json={"game_date": "2026-04-10", "innings_pitched": "5"})
    client.post(f"/api/pitchers/{pid}/goals", json={"stat_key": "era", "target": 3})
    assert client.delete("/api/auth/me").status_code == 204
    with db_module.SessionLocal() as db:
        assert db.scalar(select(User)) is None
        assert db.scalar(select(Pitcher)) is None
        assert db.scalar(select(Appearance)) is None


# --- profiles, photos, games ----------------------------------------------------------------------

def test_profile_fields_and_photo(client):
    signup(client)
    pid = client.post("/api/pitchers", json={"name": "Me", "hometown": "Tampa, FL"}).json()["id"]
    r = client.patch(f"/api/pitchers/{pid}", json={"hometown": "Austin, TX", "role": "RP"})
    assert r.json()["hometown"] == "Austin, TX" and r.json()["role"] == "RP"
    assert r.json()["name"] == "Me"  # untouched fields are kept

    png = bytes([0x89]) + b"PNG\r\n\x1a\n" + bytes(32)
    r = client.post(f"/api/pitchers/{pid}/photo", files={"file": ("me.png", png, "image/png")})
    url = r.json()["photo_url"]
    assert url.startswith("/uploads/pitchers/") and url.endswith(".png")
    assert client.get(url).content == png

    bad = client.post(f"/api/pitchers/{pid}/photo",
                      files={"file": ("x.png", b"<script>", "image/png")})
    assert bad.status_code == 400

    client.delete(f"/api/pitchers/{pid}/photo")
    assert client.get(url).status_code == 404


def test_levels_portal_and_filters(client):
    signup(client)
    portal = client.post("/api/pitchers", json={
        "name": "Portal Pete", "level": "NCAA", "class_year": "JR", "in_portal": True}).json()
    assert portal["level"] == "NCAA" and portal["in_portal"] is True
    prep = client.post("/api/pitchers", json={
        "name": "Prep Pat", "level": "HS", "class_year": "2027", "affiliation": "Texas"}).json()
    client.post("/api/pitchers", json={"name": "Pro Paul", "level": "AA", "affiliation": "NYY"})
    client.post("/api/pitchers", json={"name": "No Level"})

    names = lambda qs: {p["name"] for p in client.get(f"/api/pitchers{qs}").json()}
    assert names("?portal=true") == {"Portal Pete"}
    assert names("?level=HS&level=AA") == {"Prep Pat", "Pro Paul"}
    assert len(names("")) == 4

    # moving a player out of college clears the portal flag; turning pro clears the class year
    r = client.patch(f"/api/pitchers/{portal['id']}", json={"level": "A"}).json()
    assert r["in_portal"] is False and r["class_year"] is None
    # only college players can be in the portal
    r = client.patch(f"/api/pitchers/{prep['id']}", json={"in_portal": True}).json()
    assert r["in_portal"] is False

    bad = client.post("/api/pitchers", json={"name": "X", "level": "Little League"})
    assert bad.status_code == 422
    bad = client.post("/api/pitchers", json={"name": "Y", "level": "NCAA", "class_year": "junior"})
    assert bad.status_code == 422


def test_manual_game_entry(client):
    signup(client)
    pid = client.post("/api/pitchers", json={"name": "Me"}).json()["id"]
    game = {"game_date": "2026-04-10", "opponent": "bos", "innings_pitched": "6.2",
            "hits": 5, "runs": 2, "earned_runs": 2, "walks": 2, "strikeouts": 8}
    r = client.post(f"/api/pitchers/{pid}/games", json=game)
    assert r.status_code == 201, r.text
    assert r.json()["innings_pitched"] == "6.2" and r.json()["opponent"] == "BOS"
    assert r.json()["batters_faced"] == 20 + 5 + 2  # estimated

    assert client.post(f"/api/pitchers/{pid}/games",
                       json={**game, "opponent": "BOS"}).status_code == 409
    assert client.post(f"/api/pitchers/{pid}/games",
                       json={**game, "innings_pitched": "6.3"}).status_code == 422
    assert client.post(f"/api/pitchers/{pid}/games",
                       json={**game, "game_date": "2026-04-15", "earned_runs": 3}).status_code == 422

    stats = client.get(f"/api/pitchers/{pid}").json()["stats"]
    assert stats["era"] == round(2 / (20 / 3) * 9, 2)
    assert stats["zone_pct"] is None  # no pitch data

    gid = r.json()["id"]
    assert client.delete(f"/api/pitchers/{pid}/games/{gid}").status_code == 204
    assert client.get(f"/api/pitchers/{pid}/games").json() == []


# --- dashboard, preferences, goals, insights ------------------------------------------------------

def test_track_untrack_and_dashboard(client):
    league = make_public_pitcher()
    signup(client)
    assert client.put(f"/api/me/tracked/{league}").status_code == 204
    assert client.put(f"/api/me/tracked/{league}").status_code == 204  # idempotent
    players = client.get("/api/me/dashboard").json()["players"]
    assert len(players) == 1
    p = players[0]
    assert p["pitcher"]["is_public"] and p["season"]["pitches"] == 1
    assert p["recent"] is None  # one game isn't enough for a recent-form comparison
    client.delete(f"/api/me/tracked/{league}")
    assert client.get("/api/me/dashboard").json()["players"] == []


def test_dashboard_requires_sign_in(client):
    assert client.get("/api/me/dashboard").status_code == 401


def test_preferences_are_saved_and_validated(client):
    signup(client)
    r = client.put("/api/me/preferences", json={"tiles": ["era", "whiff_pct"]})
    assert r.json()["preferences"] == {"tiles": ["era", "whiff_pct"]}
    assert client.get("/api/auth/me").json()["preferences"]["tiles"] == ["era", "whiff_pct"]
    assert client.put("/api/me/preferences", json={"tiles": ["nope"]}).status_code == 422
    client.put("/api/me/preferences", json={"tiles": None})  # back to defaults
    assert client.get("/api/auth/me").json()["preferences"]["tiles"] is None


def test_goals(client, anon):
    signup(client)
    pid = client.post("/api/pitchers", json={"name": "Me"}).json()["id"]
    client.post(f"/api/pitchers/{pid}/games", json={
        "game_date": "2026-04-10", "innings_pitched": "9", "earned_runs": 2, "runs": 2})
    r = client.post(f"/api/pitchers/{pid}/goals", json={"stat_key": "era", "target": 3.0})
    assert r.status_code == 201
    assert r.json()["status"] == "met" and r.json()["season"] == 2.0
    assert client.post(f"/api/pitchers/{pid}/goals",
                       json={"stat_key": "zone_pct", "target": 50}).status_code == 422
    assert client.post(f"/api/pitchers/{pid}/goals",
                       json={"stat_key": "made_up", "target": 1}).status_code == 422

    goals = client.get(f"/api/pitchers/{pid}/goals").json()
    assert [g["stat_key"] for g in goals] == ["era"]
    signup(anon, "other@example.com")
    assert anon.delete(f"/api/goals/{goals[0]['id']}").status_code == 404
    assert client.delete(f"/api/goals/{goals[0]['id']}").status_code == 204


def test_evaluate_goal_statuses():
    windows = {"season": {"bb_per_9": 4.5, "k_per_9": 10.0},
               "recent": {"bb_per_9": 3.8, "k_per_9": 8.0}}
    assert evaluate_goal("k_per_9", 9.0, windows)["status"] == "met"
    assert evaluate_goal("bb_per_9", 3.5, windows)["status"] == "on_track"  # recent improving
    assert evaluate_goal("bb_per_9", 3.5, {**windows, "recent": {"bb_per_9": 5.0}})["status"] \
        == "off_track"
    assert evaluate_goal("bb_per_9", 3.5, {"season": {"bb_per_9": None}, "recent": None})[
        "status"] == "no_data"


def test_trend_insights_flag_direction_correctly():
    windows = {"season": {"bb_per_9": 3.0, "k_pct": 25.0, "whiff_pct": 30.0},
               "recent": {"bb_per_9": 4.5, "k_pct": 30.0, "whiff_pct": 31.0},
               "recent_games": 5}
    items = {i["stat_key"]: i for i in trend_insights(windows)}
    assert items["bb_per_9"]["kind"] == "declining"  # more walks is worse
    assert items["k_pct"]["kind"] == "improving"
    assert "whiff_pct" not in items  # +1 point is under the threshold
    assert trend_insights({**windows, "recent": None}) == []


def test_pitch_mix_insights():
    def p(t, n, usage, whiff, csw):
        return {"pitch_type": t, "pitches": n, "usage_pct": usage, "whiff_pct": whiff,
                "csw_pct": csw}
    items = pitch_mix_insights([p("FF", 500, 55, 20, 30), p("CH", 200, 30, 18, 22),
                                p("SL", 150, 15, 42, 35)])
    titles = " ".join(i["title"] for i in items)
    assert "slider has your best whiff rate" in titles
    assert "changeup wins the fewest pitches" in titles
    assert pitch_mix_insights([p("FF", 10, 100, 20, 30)]) == []  # too few pitches


def test_insights_endpoint(client):
    pid = make_public_pitcher()
    body = client.get(f"/api/pitchers/{pid}/insights").json()
    assert body == {"recent_games": 5, "has_recent": False, "items": []}  # one pitch: no signal


# --- schema migration -----------------------------------------------------------------------------

def test_init_db_migrates_an_old_database():
    from sqlalchemy import create_engine, inspect, text
    from app.db import init_db
    eng = create_engine("sqlite://", poolclass=StaticPool)
    with eng.begin() as conn:  # pitchers table from before accounts, photos and hometowns
        conn.execute(text("CREATE TABLE pitchers (id INTEGER PRIMARY KEY, name VARCHAR(100), "
                          "team VARCHAR(10), throws VARCHAR(1), role VARCHAR(2))"))
        conn.execute(text("CREATE UNIQUE INDEX ix_pitchers_name ON pitchers (name)"))
        conn.execute(text("INSERT INTO pitchers (name, team, throws, role) "
                          "VALUES ('Sam', '', 'R', 'SP')"))
    init_db(eng)
    insp = inspect(eng)
    assert {"hometown", "photo_url", "owner_id"} <= {c["name"] for c in insp.get_columns("pitchers")}
    with eng.begin() as conn:  # same name, different owner: now allowed
        conn.execute(text("INSERT INTO users (id, email, display_name, password_hash, created_at) "
                          "VALUES (1, 'a@b.co', 'A', 'x', '2026-01-01')"))
        conn.execute(text("INSERT INTO pitchers (name, team, throws, role, owner_id) "
                          "VALUES ('Sam', '', 'R', 'SP', 1)"))
    init_db(eng)  # idempotent
