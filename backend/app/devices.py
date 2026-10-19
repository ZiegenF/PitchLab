"""Import pitch-tracking device exports: TrackMan and Rapsodo session CSVs.

Each export is translated into Statcast-shaped rows and loaded through ingest.ingest_rows, so
games, box scores and stats work exactly as they do for a Savant upload.

TrackMan (the standard per-pitch CSV a team exports after a game or bullpen). Columns used:

    Pitcher, Date, PitcherThrows, PitcherTeam, BatterTeam, Inning, Balls, Strikes,
    TaggedPitchType (AutoPitchType as a fallback), PitchCall, KorBB, PlayResult, OutsOnPlay,
    RunsScored, RelSpeed, SpinRate, InducedVertBreak, HorzBreak, Extension, RelHeight,
    PlateLocSide, PlateLocHeight

  TrackMan already reports movement the way we store it (inches, horizontal positive to the
  pitcher's right) and plate location the way Statcast does (feet, catcher's view), so values
  pass through unchanged. Outcomes come from KorBB / PlayResult / OutsOnPlay; TrackMan has no
  earned/unearned split, so like any derived box score all runs count as earned.

Rapsodo (a bullpen export from the Rapsodo app). Rapsodo puts a few "Player Name: ..." style
lines above the column header; we find the header row and read the name from those lines.
Only fields whose meaning is unambiguous are loaded: pitch type, velocity, total spin, release
height and extension. Rapsodo's break and strike-zone columns are left out until their sign
conventions are confirmed against a real export.
"""

import csv
import io
import re
from datetime import datetime

from sqlalchemy.orm import Session

from .ingest import ingest_csv, ingest_rows
from .models import SOURCE_RAPSODO, SOURCE_TRACKMAN

BULLPEN = "BULLPEN"

# Device pitch-type names -> Statcast codes (lowercased, spaces and dashes removed)
PITCH_TYPES = {
    "fastball": "FF", "fourseamfastball": "FF", "fourseam": "FF", "4seam": "FF",
    "twoseamfastball": "SI", "twoseam": "SI", "2seam": "SI", "sinker": "SI",
    "cutter": "FC", "slider": "SL", "sweeper": "ST", "slurve": "SV",
    "curveball": "CU", "knucklecurve": "KC", "changeup": "CH", "splitter": "FS",
    "knuckleball": "KN",
}

# TrackMan PitchCall -> Statcast description
PITCH_CALLS = {
    "ballcalled": "ball", "ballindirt": "blocked_ball", "ballintentional": "intent_ball",
    "strikecalled": "called_strike", "strikeswinging": "swinging_strike",
    "foulball": "foul", "foulballnotfieldable": "foul", "foulballfieldable": "foul",
    "foultip": "foul_tip", "inplay": "hit_into_play", "hitbypitch": "hit_by_pitch",
}

# TrackMan PlayResult -> Statcast event (outs come from OutsOnPlay)
HITS = {"single": "single", "double": "double", "triple": "triple", "homerun": "home_run"}


def _key(v) -> str:
    return re.sub(r"[\s\-_]", "", (v or "").strip().lower())


def parse_date(raw: str) -> str | None:
    """'2025-04-12', '2025/04/12', '4/12/2025', '4/12/25', with or without a time -> ISO date."""
    raw = (raw or "").strip()
    if not raw:
        return None
    day = raw.split("T")[0].split(" ")[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(day, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"unrecognized date {raw!r}")


def pitch_type(*names: str) -> str:
    for name in names:
        code = PITCH_TYPES.get(_key(name))
        if code:
            return code
    return "UN"


# --- TrackMan -------------------------------------------------------------------------------

def is_trackman(header: list[str]) -> bool:
    return {"Pitcher", "PitchCall", "RelSpeed"} <= set(header)


def _trackman_event(r: dict) -> str:
    """The Statcast-style event for a TrackMan row; '' if the plate appearance continues."""
    korbb, play = _key(r.get("KorBB")), _key(r.get("PlayResult"))
    outs = int(float(r.get("OutsOnPlay") or 0))
    if korbb == "strikeout":
        return "strikeout"
    if korbb == "walk":
        return "walk"
    if _key(r.get("PitchCall")) == "hitbypitch":
        return "hit_by_pitch"
    if play in HITS:
        return HITS[play]
    if play == "out":
        return {2: "double_play", 3: "triple_play"}.get(outs, "field_out")
    if play == "fielderschoice":
        return "fielders_choice_out" if outs else "fielders_choice"
    if play == "sacrifice":
        return "sac_fly"
    if play == "error":
        return "field_error"
    return ""


def trackman_rows(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        date = parse_date(r.get("Date", ""))
        call = PITCH_CALLS.get(_key(r.get("PitchCall")), "unknown")
        runs = int(float(r.get("RunsScored") or 0))
        rows.append({
            "player_name": r.get("Pitcher", ""),
            "game_date": date or "",
            "team": r.get("PitcherTeam", ""),
            "opponent": (r.get("BatterTeam") or "").strip() or BULLPEN,
            "p_throws": (r.get("PitcherThrows") or "R")[:1],
            "pitch_type": pitch_type(r.get("TaggedPitchType"), r.get("AutoPitchType")),
            "release_speed": r.get("RelSpeed"),
            "release_spin_rate": r.get("SpinRate"),
            "plate_x": r.get("PlateLocSide"),
            "plate_z": r.get("PlateLocHeight"),
            "ivb": r.get("InducedVertBreak"),
            "hb": r.get("HorzBreak"),
            "release_extension": r.get("Extension"),
            "release_pos_z": r.get("RelHeight"),
            "description": call,
            "events": _trackman_event(r),
            "inning": r.get("Inning") or 1,
            "balls": r.get("Balls") or 0,
            "strikes": r.get("Strikes") or 0,
            "bat_score": 0,
            "post_bat_score": runs,
        })
    return rows


# --- Rapsodo --------------------------------------------------------------------------------

RAPSODO_COLUMNS = {  # our field -> accepted Rapsodo header names (compared with _key)
    "pitch_type": ("Pitch Type",),
    "date": ("Date", "Date Time", "Pitch Time"),
    "velocity": ("Velocity", "Speed", "Pitch Speed"),
    "spin": ("Total Spin", "Spin Rate", "Spin"),
    "release_height": ("Release Height", "Release Height (ft)"),
    "extension": ("Release Extension", "Release Extension (ft)", "Extension"),
    "name": ("Player Name", "Pitcher", "Name"),
}


def _rapsodo_header_index(lines: list[list[str]]) -> int | None:
    for i, cells in enumerate(lines[:30]):
        keys = {_key(c) for c in cells}
        if "pitchtype" in keys and keys & {"velocity", "speed", "pitchspeed"}:
            return i
    return None


def is_rapsodo(lines: list[list[str]]) -> bool:
    return _rapsodo_header_index(lines) is not None


def rapsodo_rows(lines: list[list[str]], pitcher_name: str | None = None) -> list[dict]:
    start = _rapsodo_header_index(lines)
    header = [_key(c) for c in lines[start]]

    def col(field):
        for name in RAPSODO_COLUMNS[field]:
            if _key(name) in header:
                return header.index(_key(name))
        return None

    # "Player Name:,Jane Doe" style lines above the table
    name_above = None
    for cells in lines[:start]:
        if cells and _key(cells[0]).rstrip(":") == "playername" and len(cells) > 1:
            name_above = cells[1].strip()
    idx = {f: col(f) for f in RAPSODO_COLUMNS}
    if idx["date"] is None:
        raise ValueError("no Date column found in the Rapsodo export")

    def get(cells, field):
        i = idx[field]
        return cells[i].strip() if i is not None and i < len(cells) else ""

    rows = []
    for cells in lines[start + 1:]:
        if not any(c.strip() for c in cells):
            continue
        name = get(cells, "name") or name_above or pitcher_name
        if not name:
            raise ValueError("couldn't find the pitcher's name in the Rapsodo export")
        rows.append({
            "player_name": name,
            "game_date": parse_date(get(cells, "date")) or "",
            "opponent": BULLPEN,
            "pitch_type": pitch_type(get(cells, "pitch_type")),
            "release_speed": get(cells, "velocity"),
            "release_spin_rate": get(cells, "spin"),
            "release_pos_z": get(cells, "release_height"),
            "release_extension": get(cells, "extension"),
            "description": "unknown",
            "inning": 1,
        })
    return rows


# --- entry point ----------------------------------------------------------------------------

def detect_and_ingest(db: Session, content: bytes, owner_id: int | None = None) -> dict:
    """Load a TrackMan, Rapsodo or Statcast CSV, telling them apart by their headers."""
    text = content.decode("utf-8-sig")
    lines = list(csv.reader(io.StringIO(text)))
    if not lines:
        raise ValueError("the file is empty")
    if is_trackman(lines[0]):
        records = list(csv.DictReader(io.StringIO(text)))
        result = ingest_rows(db, trackman_rows(records), owner_id=owner_id, source=SOURCE_TRACKMAN)
        return {**result, "format": "trackman"}
    if is_rapsodo(lines):
        result = ingest_rows(db, rapsodo_rows(lines), owner_id=owner_id, source=SOURCE_RAPSODO)
        return {**result, "format": "rapsodo"}
    return {**ingest_csv(db, content, owner_id=owner_id), "format": "statcast"}
