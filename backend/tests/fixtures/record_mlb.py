"""Re-record the real MLB responses used by test_sync_mlb.py (needs network).

    cd backend && python -m tests.fixtures.record_mlb
"""

import csv
import gzip
import io
import json
from pathlib import Path

from app.mlb import MlbClient

PITCHER, SEASON = 669373, 2024  # Tarik Skubal
OUT = Path(__file__).parent / "skubal_2024"
STATCAST_COLUMNS = [
    "pitch_type", "game_date", "release_speed", "release_spin_rate", "plate_x", "plate_z",
    "player_name", "pitcher", "events", "description", "inning", "balls", "strikes",
    "inning_topbot", "home_team", "away_team", "p_throws", "bat_score", "post_bat_score",
    "game_pk", "game_type",
]


def main():
    c = MlbClient()
    log = c.game_log(PITCHER, SEASON, 1)
    used = {s["team"]["id"] for s in log} | {s["opponent"]["id"] for s in log}
    teams = [{k: t.get(k) for k in ("id", "name", "abbreviation", "parentOrgId")}
             for i, t in c.teams(SEASON).items() if i in used]
    log = [{**{k: s[k] for k in ("date", "gameType", "isHome", "team", "opponent", "game") if k in s},
            "stat": s["stat"]} for s in log]
    OUT.mkdir(exist_ok=True)
    (OUT / "stats_api.json").write_text(json.dumps({
        "person": c.person(PITCHER), "teams": teams, "game_log": log,
        "season_line": c.season_line(PITCHER, SEASON, 1),
    }, indent=1), encoding="utf-8")

    rows = c.statcast(PITCHER, SEASON)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=STATCAST_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    with gzip.open(OUT / "statcast.csv.gz", "wt", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())
    print(f"{len(log)} games, {len(rows)} Statcast rows -> {OUT}")


if __name__ == "__main__":
    main()
