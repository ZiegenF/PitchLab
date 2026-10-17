"""Thin client for MLB's public data: the Stats API (official box scores) and Baseball Savant
(Statcast pitch-by-pitch). It only fetches; turning responses into rows is sync_mlb's job, so
tests can swap this for recorded responses.

Both are free and keyless. MLB's terms allow personal, non-commercial use:
http://gdx.mlb.com/components/copyright.txt
"""

import csv
import io

import httpx

STATS_API = "https://statsapi.mlb.com/api/v1"
SAVANT_CSV = "https://baseballsavant.mlb.com/statcast_search/csv"
HEADSHOT = ("https://img.mlbstatic.com/mlb-photos/image/upload/"
            "d_people:generic:headshot:67:current.png/w_213,q_auto:best/v1/people/{id}/headshot/67/current")

# Stats API sport ids -> our levels. Statcast pitch data is only fetched for MLB.
SPORT_LEVELS = {1: "MLB", 11: "AAA", 12: "AA", 13: "A+", 14: "A"}


class MlbClient:
    def __init__(self, timeout: float = 30.0):
        self.http = httpx.Client(timeout=timeout, follow_redirects=True,
                                 headers={"User-Agent": "PitchLab (personal project)"})

    def _json(self, path: str, **params) -> dict:
        r = self.http.get(f"{STATS_API}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def search(self, name: str) -> list[dict]:
        """People matching a name, pitchers first."""
        people = self._json("/people/search", names=name).get("people", [])
        return sorted(people, key=lambda p: p.get("primaryPosition", {}).get("code") not in ("1", "Y"))

    def person(self, mlbam_id: int) -> dict:
        return self._json(f"/people/{mlbam_id}")["people"][0]

    def teams(self, season: int) -> dict[int, dict]:
        sports = ",".join(str(s) for s in SPORT_LEVELS)
        return {t["id"]: t for t in self._json("/teams", sportIds=sports, season=season)["teams"]}

    def _stats(self, mlbam_id: int, kind: str, season: int, sport_id: int) -> list[dict]:
        data = self._json(f"/people/{mlbam_id}/stats", stats=kind, group="pitching",
                          season=season, sportId=sport_id)
        return data["stats"][0]["splits"] if data.get("stats") else []

    def game_log(self, mlbam_id: int, season: int, sport_id: int) -> list[dict]:
        return self._stats(mlbam_id, "gameLog", season, sport_id)

    def season_line(self, mlbam_id: int, season: int, sport_id: int) -> dict | None:
        """The official season totals at one level, or None if he didn't pitch there."""
        splits = self._stats(mlbam_id, "season", season, sport_id)
        return splits[0]["stat"] if splits else None

    def statcast(self, mlbam_id: int, season: int) -> list[dict]:
        """Every regular-season MLB pitch he threw that season, as Savant CSV rows."""
        r = self.http.get(SAVANT_CSV, timeout=180, params={
            "all": "true", "type": "details", "player_type": "pitcher",
            "pitchers_lookup[]": mlbam_id, "hfSea": f"{season}|", "hfGT": "R|",
        })
        r.raise_for_status()
        return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
