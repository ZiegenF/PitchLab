"""TrackMan and Rapsodo imports.

The files here are hand-built in each device's export layout (TrackMan's standard column names;
Rapsodo's name lines above the table), not real exports, so they test our mapping, not the
devices. Check a real export with the device's own report before trusting new numbers.
"""

import csv
import io

from app.devices import parse_date, pitch_type

from .test_api import client, signup  # noqa: F401  (client is a fixture)

TRACKMAN_HEADER = [
    "PitchNo", "Date", "Time", "Pitcher", "PitcherId", "PitcherThrows", "PitcherTeam", "Batter",
    "BatterSide", "BatterTeam", "Inning", "Top/Bottom", "Outs", "Balls", "Strikes",
    "TaggedPitchType", "AutoPitchType", "PitchCall", "KorBB", "PlayResult", "OutsOnPlay",
    "RunsScored", "RelSpeed", "SpinRate", "SpinAxis", "RelHeight", "RelSide", "Extension",
    "InducedVertBreak", "HorzBreak", "PlateLocHeight", "PlateLocSide",
]


def tm(call, balls=0, strikes=0, korbb="Undefined", play="Undefined", outs=0, runs=0,
       pitch="Fastball", auto="Four-Seam", date="3/14/2026", batter_team="UTA_UTE",
       pitcher="Doe, Jane", **kw):
    r = dict.fromkeys(TRACKMAN_HEADER, "")
    r.update(Date=date, Pitcher=pitcher, PitcherId="1000123", PitcherThrows="Right",
             PitcherTeam="BYU_COU", BatterTeam=batter_team, Inning="1", Balls=balls,
             Strikes=strikes, TaggedPitchType=pitch, AutoPitchType=auto, PitchCall=call,
             KorBB=korbb, PlayResult=play, OutsOnPlay=outs, RunsScored=runs, RelSpeed="92.4",
             SpinRate="2350", RelHeight="5.9", Extension="6.4", InducedVertBreak="17.2",
             HorzBreak="9.1", PlateLocHeight="2.6", PlateLocSide="-0.3")
    r.update(kw)
    return r


def to_csv(rows, header=TRACKMAN_HEADER):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


def post(client, content, name="session.csv"):
    return client.post("/api/ingest/csv", files={"file": (name, content, "text/csv")})


GAME = [
    # strikeout (two swinging, then caught looking)
    tm("StrikeSwinging"), tm("StrikeSwinging", strikes=1),
    tm("StrikeCalled", strikes=2, korbb="Strikeout"),
    # walk
    tm("BallCalled"), tm("BallCalled", balls=1), tm("BallCalled", balls=2),
    tm("BallinDirt", balls=3, korbb="Walk", pitch="ChangeUp"),
    # single, two-run homer, double play, hit by pitch
    tm("InPlay", play="Single", pitch="Sinker"),
    tm("InPlay", play="HomeRun", runs=2),
    tm("InPlay", play="Out", outs=2, pitch="Undefined", auto="Slider"),
    tm("HitByPitch"),
]


def player(client, name):
    return next(p for p in client.get("/api/pitchers").json() if p["name"] == name)


def test_trackman_game_becomes_box_score_and_pitches(client):
    signup(client)
    r = post(client, to_csv(GAME))
    assert r.status_code == 200, r.text
    assert r.json() == {"pitchers": 1, "appearances": 1, "pitches": 11, "skipped_rows": 0,
                        "format": "trackman"}

    p = player(client, "Jane Doe")
    assert p["source"] == "trackman" and p["team"] == "BYU_COU" and p["throws"] == "R"
    game = client.get(f"/api/pitchers/{p['id']}/games").json()[0]
    assert game["game_date"] == "2026-03-14" and game["opponent"] == "UTA_UTE"
    # six batters: K, BB, 1B, HR, double play, HBP
    assert (game["innings_pitched"], game["batters_faced"], game["strikeouts"], game["walks"],
            game["hits"], game["home_runs"], game["runs"], game["earned_runs"]) == \
        ("1.0", 6, 1, 1, 2, 1, 2, 2)


def test_trackman_values_pass_through_in_our_units(client):
    signup(client)
    post(client, to_csv(GAME))
    pid = player(client, "Jane Doe")["id"]
    pitches = client.get(f"/api/pitchers/{pid}/pitches").json()
    ff = next(x for x in pitches if x["pitch_type"] == "FF")
    assert (ff["velocity"], ff["spin_rate"], ff["ivb"], ff["hb"], ff["extension"],
            ff["release_height"], ff["plate_x"], ff["plate_z"]) == \
        (92.4, 2350, 17.2, 9.1, 6.4, 5.9, -0.3, 2.6)
    # tagged type first, the automatic one when the tag is Undefined
    assert sorted({x["pitch_type"] for x in pitches}) == ["CH", "FF", "SI", "SL"]
    results = [x["result"] for x in sorted(pitches, key=lambda x: x["id"])]
    assert results[:4] == ["swinging_strike", "swinging_strike", "called_strike", "ball"]


def test_trackman_bullpen_has_no_outcome_stats(client):
    """A bullpen has location but no batter or umpire: Zone% is real, CSW% has no data."""
    signup(client)
    pen = [tm("Undefined", pitcher="Pen, Pete", batter_team="", PlateLocSide=str(side))
           for side in (0.0, 0.1, 1.5, -2.0)]
    assert post(client, to_csv(pen)).status_code == 200
    p = player(client, "Pete Pen")
    assert client.get(f"/api/pitchers/{p['id']}/games").json()[0]["opponent"] == "BULLPEN"
    stats = client.get(f"/api/pitchers/{p['id']}").json()["stats"]
    assert stats["zone_pct"] == 50.0
    assert stats["csw_pct"] is None and stats["whiff_pct"] is None and stats["f_strike_pct"] is None


RAPSODO = """Player ID:,48213
Player Name:,Sam Lefty
No,Date,Pitch Type,Is Strike,Strike Zone Side,Strike Zone Height,Velocity,Total Spin,Spin Efficiency (release),VB (trajectory),HB (trajectory),Release Height,Release Side,Release Extension (ft)
1,2026-10-15 14:03:22,Fastball,YES,-3.2,25.1,88.4,2210,95.1,15.2,-8.1,5.71,-1.9,6.10
2,2026-10-15 14:03:51,CurveBall,NO,4.0,12.2,72.1,2380,80.0,-9.8,6.3,5.68,-1.9,5.95
3,2026-10-15 14:04:30,ChangeUp,YES,1.1,20.4,79.6,1650,88.0,7.5,-12.4,5.70,-2.0,6.05
"""


def test_rapsodo_bullpen_loads_the_unambiguous_fields(client):
    signup(client)
    r = post(client, RAPSODO.encode())
    assert r.status_code == 200, r.text
    assert r.json()["format"] == "rapsodo" and r.json()["pitches"] == 3

    p = player(client, "Sam Lefty")
    assert p["source"] == "rapsodo"
    pitches = sorted(client.get(f"/api/pitchers/{p['id']}/pitches").json(), key=lambda x: x["id"])
    assert [(x["pitch_type"], x["velocity"], x["spin_rate"]) for x in pitches] == \
        [("FF", 88.4, 2210), ("CU", 72.1, 2380), ("CH", 79.6, 1650)]
    assert (pitches[0]["release_height"], pitches[0]["extension"]) == (5.71, 6.1)
    # break and location conventions aren't confirmed for Rapsodo, so they aren't loaded
    assert all(x["hb"] is None and x["ivb"] is None and x["plate_x"] is None for x in pitches)
    assert {x["result"] for x in pitches} == {"unknown"}


def test_rapsodo_without_a_name_is_rejected(client):
    signup(client)
    nameless = "\n".join(RAPSODO.splitlines()[2:])
    r = post(client, nameless.encode())
    assert r.status_code == 400 and "name" in r.json()["detail"]


def test_date_and_pitch_type_parsing():
    assert parse_date("3/14/2026") == parse_date("2026-03-14") == parse_date("3/14/26 7:05 PM")
    assert parse_date("2026/03/14 19:05:00") == "2026-03-14"
    assert pitch_type("FourSeamFastBall") == pitch_type("Four-Seam") == "FF"
    assert pitch_type("Undefined", "Sweeper") == "ST"
    assert pitch_type("Other", "") == "UN"
