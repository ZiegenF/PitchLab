"""Keep synced MLB and minor-league pitchers current while the API runs.

Any pitcher synced for the current season whose last sync is older than PITCHLAB_SYNC_HOURS
(default 6; 0 turns auto-sync off) is re-synced from MLB and re-checked against the official
totals, so new games show up without anyone running sync_mlb by hand. Past seasons are final
and left alone. It runs in a background thread; GET /api/sync/status reports the last run.
"""

import logging
import os
import threading
from datetime import date, timedelta

from sqlalchemy import select

from .auth import utcnow
from .db import SessionLocal
from .mlb import MlbClient
from .models import SOURCE_MLB, Pitcher
from .sync_mlb import sync_pitcher

log = logging.getLogger("pitchlab.autosync")

INTERVAL_HOURS = float(os.getenv("PITCHLAB_SYNC_HOURS", "6"))
CHECK_EVERY_SECONDS = 600  # how often to look for pitchers that are due

status = {"enabled": INTERVAL_HOURS > 0, "interval_hours": INTERVAL_HOURS,
          "last_run": None, "results": []}


def due(db, season: int, now=None) -> list[Pitcher]:
    cutoff = (now or utcnow()) - timedelta(hours=INTERVAL_HOURS)
    synced = db.scalars(select(Pitcher).where(Pitcher.source == SOURCE_MLB,
                                              Pitcher.owner_id.is_(None)))
    return [p for p in synced
            if (p.verification or {}).get("season") == season
            and (p.synced_at is None or p.synced_at < cutoff)]


def run_once(client=None, season: int | None = None, session_factory=None) -> list[dict]:
    """Re-sync every pitcher that's due. Returns one result per pitcher."""
    season = season or date.today().year
    client = client or MlbClient()
    results = []
    with (session_factory or SessionLocal)() as db:
        for mlbam_id, name in [(p.mlbam_id, p.name) for p in due(db, season)]:
            try:
                p = sync_pitcher(db, client, mlbam_id, season)
            except Exception as e:  # one bad player shouldn't stop the rest
                db.rollback()
                log.warning("auto-sync failed for %s (%s): %s", name, mlbam_id, e)
                results.append({"name": name, "verified": False, "error": str(e)})
                continue
            results.append({"name": p.name, "verified": p.verification["ok"], "error": None})
    if results:
        status.update(last_run=utcnow().isoformat(timespec="seconds"), results=results)
    return results


def _loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            run_once()
        except Exception:
            log.exception("auto-sync run failed")
        stop.wait(CHECK_EVERY_SECONDS)


def start() -> threading.Event | None:
    """Start the background thread; set the returned event to stop it."""
    if not status["enabled"]:
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(stop,), name="autosync", daemon=True).start()
    return stop
