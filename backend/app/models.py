from datetime import date, datetime

from sqlalchemy import (JSON, Date, DateTime, Float, ForeignKey, Integer, String,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# Where a pitcher's data came from (Pitcher.source)
SOURCE_SIMULATED = "simulated"  # generated demo data, not real
SOURCE_MLB = "mlb"  # synced from the MLB Stats API (+ Statcast)
SOURCE_CSV = "csv"  # uploaded Statcast-format CSV
SOURCE_TRACKMAN = "trackman"  # uploaded TrackMan session export
SOURCE_RAPSODO = "rapsodo"  # uploaded Rapsodo session export
SOURCE_MANUAL = "manual"  # entered by hand

# Where one game's box score came from (Appearance.source)
BOX_OFFICIAL = "official"  # official scorer, via the MLB Stats API
BOX_DERIVED = "derived"  # counted from pitch-by-pitch events (all runs treated as earned)
BOX_MANUAL = "manual"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    preferences: Mapped[dict | None] = mapped_column(JSON)  # {"tiles": ["era", ...]}


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 of the cookie value
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    user: Mapped[User] = relationship()


class Pitcher(Base):
    """owner_id NULL = public league data (read-only); otherwise private to that user."""

    __tablename__ = "pitchers"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_pitchers_owner_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                                 index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    team: Mapped[str] = mapped_column(String(10), default="")
    throws: Mapped[str] = mapped_column(String(1), default="R")  # R / L
    role: Mapped[str] = mapped_column(String(2), default="SP")  # SP / RP
    hometown: Mapped[str | None] = mapped_column(String(120))  # "Tampa, FL" / "Santo Domingo, DR"
    photo_url: Mapped[str | None] = mapped_column(String(255))  # served from /uploads
    # HS / NCAA / A / A+ / AA / AAA / MLB; NULL = not set yet (e.g. from a CSV upload)
    level: Mapped[str | None] = mapped_column(String(4))
    class_year: Mapped[str | None] = mapped_column(String(4))  # NCAA: FR..GR, HS: grad year
    affiliation: Mapped[str | None] = mapped_column(String(60))  # MiLB parent club / HS commit
    in_portal: Mapped[bool | None] = mapped_column(default=False)  # NCAA transfer portal
    source: Mapped[str | None] = mapped_column(String(12))  # SOURCE_*
    mlbam_id: Mapped[int | None] = mapped_column(Integer, index=True)  # MLB's player id
    synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    # last check against official totals, see sync_mlb.reconcile
    verification: Mapped[dict | None] = mapped_column(JSON)

    appearances: Mapped[list["Appearance"]] = relationship(
        back_populates="pitcher", cascade="all, delete-orphan", order_by="Appearance.game_date"
    )


class TrackedPitcher(Base):
    """A pitcher on a user's dashboard."""

    __tablename__ = "tracked_pitchers"
    __table_args__ = (UniqueConstraint("user_id", "pitcher_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pitcher_id: Mapped[int] = mapped_column(ForeignKey("pitchers.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Goal(Base):
    """A user's target for one stat of one pitcher, e.g. BB/9 at or under 3.0."""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pitcher_id: Mapped[int] = mapped_column(ForeignKey("pitchers.id", ondelete="CASCADE"),
                                            index=True)
    stat_key: Mapped[str] = mapped_column(String(40))
    target: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Appearance(Base):
    """One pitcher's line in one game (the box score row)."""

    __tablename__ = "appearances"
    __table_args__ = (UniqueConstraint("pitcher_id", "game_date", "opponent"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pitcher_id: Mapped[int] = mapped_column(ForeignKey("pitchers.id"), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    opponent: Mapped[str] = mapped_column(String(10), default="")
    is_start: Mapped[bool] = mapped_column(default=True)
    outs: Mapped[int] = mapped_column(Integer, default=0)  # IP stored as outs recorded
    hits: Mapped[int] = mapped_column(Integer, default=0)
    runs: Mapped[int] = mapped_column(Integer, default=0)
    earned_runs: Mapped[int] = mapped_column(Integer, default=0)
    walks: Mapped[int] = mapped_column(Integer, default=0)
    strikeouts: Mapped[int] = mapped_column(Integer, default=0)
    home_runs: Mapped[int] = mapped_column(Integer, default=0)
    hit_by_pitch: Mapped[int] = mapped_column(Integer, default=0)
    batters_faced: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str | None] = mapped_column(String(10))  # BOX_*
    game_pk: Mapped[int | None] = mapped_column(Integer, index=True)  # MLB's game id
    level: Mapped[str | None] = mapped_column(String(4))  # level this game was played at
    official_pitches: Mapped[int | None] = mapped_column(Integer)  # official pitch count

    pitcher: Mapped[Pitcher] = relationship(back_populates="appearances")
    pitches: Mapped[list["Pitch"]] = relationship(
        back_populates="appearance", cascade="all, delete-orphan"
    )


class Pitch(Base):
    """A single pitch, Statcast-style. Plate coordinates are in feet from the catcher's view."""

    __tablename__ = "pitches"

    id: Mapped[int] = mapped_column(primary_key=True)
    appearance_id: Mapped[int] = mapped_column(ForeignKey("appearances.id"), index=True)
    pitcher_id: Mapped[int] = mapped_column(ForeignKey("pitchers.id"), index=True)
    pitch_type: Mapped[str] = mapped_column(String(4), index=True)  # FF, SI, SL, CU, CH, FC...
    velocity: Mapped[float | None] = mapped_column(Float)  # mph
    spin_rate: Mapped[float | None] = mapped_column(Float)  # rpm
    plate_x: Mapped[float | None] = mapped_column(Float)
    plate_z: Mapped[float | None] = mapped_column(Float)
    # Movement in TrackMan's convention, inches: induced vertical break (gravity removed) and
    # horizontal break, positive = to the pitcher's right. Statcast is converted to match.
    ivb: Mapped[float | None] = mapped_column(Float)
    hb: Mapped[float | None] = mapped_column(Float)
    extension: Mapped[float | None] = mapped_column(Float)  # ft in front of the rubber
    release_height: Mapped[float | None] = mapped_column(Float)  # ft above the ground
    # normalized: ball, called_strike, swinging_strike, foul, in_play, hit_by_pitch, or
    # unknown (a bullpen with no batter or umpire, e.g. most Rapsodo / TrackMan sessions)
    result: Mapped[str] = mapped_column(String(20))
    inning: Mapped[int] = mapped_column(Integer, default=1)
    balls: Mapped[int] = mapped_column(Integer, default=0)
    strikes: Mapped[int] = mapped_column(Integer, default=0)

    appearance: Mapped[Appearance] = relationship(back_populates="pitches")
