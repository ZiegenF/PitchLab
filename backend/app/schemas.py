from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Lowest to highest. "NCAA" covers every college division.
Level = Literal["HS", "NCAA", "A", "A+", "AA", "AAA", "MLB"]
CLASS_YEAR = r"^(FR|SO|JR|SR|GR|\d{4})$"  # college class, or high-school graduation year


class PitcherBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    team: str = ""
    throws: Literal["R", "L"] = "R"
    role: Literal["SP", "RP"] = "SP"
    hometown: str | None = Field(None, max_length=120)
    level: Level | None = None
    class_year: str | None = Field(None, pattern=CLASS_YEAR)
    affiliation: str | None = Field(None, max_length=60)
    in_portal: bool = False

    @field_validator("in_portal", mode="before")
    @classmethod
    def _null_is_false(cls, v):
        return bool(v)


class PitcherCreate(PitcherBase):
    pass


class PitcherUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    team: str | None = None
    throws: Literal["R", "L"] | None = None
    role: Literal["SP", "RP"] | None = None
    hometown: str | None = Field(None, max_length=120)
    level: Level | None = None
    class_year: str | None = Field(None, pattern=CLASS_YEAR)
    affiliation: str | None = Field(None, max_length=60)
    in_portal: bool | None = None


class PitcherOut(PitcherBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    photo_url: str | None = None
    is_mine: bool = False  # owned by the signed-in user (editable)
    is_public: bool = True  # league data, visible to everyone and read-only
    is_tracked: bool = False  # on the signed-in user's dashboard
    source: Literal["simulated", "mlb", "csv", "manual"] | None = None
    mlbam_id: int | None = None
    synced_at: datetime | None = None
    verification: dict | None = None  # see sync_mlb.reconcile


class PitcherListItem(PitcherOut):
    games: int
    innings_pitched: str
    era: float | None
    k_per_9: float | None
    whip: float | None
    avg_fb_velo: float | None


class AppearanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    game_date: date
    opponent: str
    is_start: bool
    innings_pitched: str
    hits: int
    runs: int
    earned_runs: int
    walks: int
    strikeouts: int
    home_runs: int
    batters_faced: int
    pitches: int
    official_pitches: int | None = None
    source: str | None = None  # official / derived / manual
    level: str | None = None


class GameCreate(BaseModel):
    """A box-score line entered by hand (no pitch-level data)."""

    game_date: date
    opponent: str = Field("", max_length=10)
    is_start: bool = True
    innings_pitched: str = Field(pattern=r"^\d{1,2}(\.[012])?$", examples=["6.2"])
    hits: int = Field(0, ge=0)
    runs: int = Field(0, ge=0)
    earned_runs: int = Field(0, ge=0)
    walks: int = Field(0, ge=0)
    strikeouts: int = Field(0, ge=0)
    home_runs: int = Field(0, ge=0)
    hit_by_pitch: int = Field(0, ge=0)
    batters_faced: int | None = Field(None, ge=0, description="Estimated if left blank")

    @property
    def outs(self) -> int:
        whole, _, part = self.innings_pitched.partition(".")
        return int(whole) * 3 + int(part or 0)


class StatDefinition(BaseModel):
    key: str
    label: str
    group: str
    digits: int
    suffix: str
    description: str
    default: bool
    better: Literal["higher", "lower"] | None


class SignupIn(BaseModel):
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    display_name: str
    preferences: dict | None = None


class PreferencesIn(BaseModel):
    tiles: list[str] | None = None  # stat keys, in display order; None = defaults


class GoalIn(BaseModel):
    stat_key: str
    target: float


class GoalOut(BaseModel):
    id: int
    pitcher_id: int
    stat_key: str
    target: float
    season: float | None
    recent: float | None
    status: Literal["met", "on_track", "off_track", "no_data"]


class PitchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pitch_type: str
    velocity: float | None
    spin_rate: float | None
    plate_x: float | None
    plate_z: float | None
    result: str
    balls: int
    strikes: int


class IngestResult(BaseModel):
    pitchers: int
    appearances: int
    pitches: int
    skipped_rows: int
