# PitchLab

[![tests](https://github.com/ZiegenF/PitchLab/actions/workflows/tests.yml/badge.svg)](https://github.com/ZiegenF/PitchLab/actions/workflows/tests.yml)

A full-stack pitching analytics app: ingest pitch-by-pitch data, compute traditional and
pitch-level stats, and visualize them. Scout pitchers from high school through MLB, track them
on your own dashboard, and sync real MLB seasons that are checked against official totals.

![Scout page: pitchers from high school to MLB as baseball cards, with level tabs and filters](docs/screenshots/scout.png)

<table>
<tr>
<td width="50%"><img src="docs/screenshots/player.png" alt="Tarik Skubal's 2024 season: stat tiles, official-data panel, Coach's Corner and Statcast arsenal"></td>
<td width="50%"><img src="docs/screenshots/split-season.png" alt="Paul Skenes's 2024 season split across Triple-A and MLB, each level matching MLB's official line"></td>
</tr>
<tr>
<td><b>Real data:</b> Tarik Skubal's 2024 season from the MLB Stats API and Statcast</td>
<td><b>Verified:</b> every level checked against MLB's official totals</td>
</tr>
</table>

**Stack:** FastAPI + SQLAlchemy · PostgreSQL (SQLite fallback for local dev) · React + Vite + Recharts

```
backend/
  app/
    models.py      Pitcher -> Appearance (box score) -> Pitch (velo, spin, location, result)
    ingest.py      Statcast CSV -> pitches + derived box-score lines
    analytics.py   ERA, WHIP, FIP, K/9...; zone%, whiff%, chase%, CSW% (SQL aggregates)
    seed.py        simulates a mock season PA by PA, then loads it through ingest.py
    routers/       REST endpoints
  tests/
frontend/src/
  components/      stat tiles, arsenal table, velo/spin trend, strike-zone plot, game log, upload
sample_data/       CSV template for logging your own bullpen sessions
```

## Run it

**Backend** (http://localhost:8000, interactive docs at `/docs`):

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed --real       # simulated league + demo account + 3 real 2024 MLB seasons
uvicorn app.main:app            # add --reload on macOS/Linux; on Windows it can hang
```

**Frontend** (http://localhost:5173; `/api` is proxied to the backend):

```bash
cd frontend
npm install
npm run dev
```

**Tests:** `cd backend && pytest`

Leave off `--real` to seed without network access.

**Demo account** (created by the seed): `demo@pitchlab.dev` / `pitchlab-demo`. It tracks league
pitchers at several levels plus one private pitcher of its own, with goals set, so every feature
has data.

## Accounts, dugouts and ownership

- **League pitchers** (loaded by the seed) are public: anyone can browse them, nobody can edit them.
- **Your pitchers** (added with **+ Add pitcher** or uploaded as CSV) are private to your account.
  Other users get a 404 for them.
- **My Dugout** is your dashboard: the pitchers you track (yours, plus any league pitcher you add
  from **Scout Players**), shown as baseball cards and in a side-by-side table with the stats you
  chose under **Customize stats**. Your stat choice is saved to your account.
- Every stat with a good/bad direction shows **▲▼ recent form**: the last 5 outings (10 for
  relievers) vs the season, labeled better or worse.
- Passwords are hashed with scrypt; sessions are random tokens in an httpOnly, SameSite=Lax
  cookie, and only the token's hash is stored. Set `COOKIE_SECURE=true` when serving over HTTPS.

## Levels and scouting

Every pitcher has a `level`: `HS`, `NCAA`, `A`, `A+`, `AA`, `AAA` or `MLB` (or none, e.g. right
after a CSV upload). Level-specific fields:

- High school: `class_year` is the graduation year (`2027`), `affiliation` the college commitment.
- College: `class_year` is `FR` / `SO` / `JR` / `SR` / `GR`, and `in_portal` marks the transfer portal.
- Minors: `affiliation` is the parent club (`NYY`).

Fields that don't fit the level are cleared on save, so a player who signs a pro contract leaves
the portal automatically. The Scout page has tabs for each level, in career order (high school →
college → portal → minors → MLB). Cycle through them with the ‹ › buttons or the arrow keys.
You can also filter by hand and role, and sort by ERA, K/9, WHIP or velocity. Filters are kept in
the URL, so you can bookmark a view like `/scout?level=portal&throws=L`. The Dugout shows the
same switcher once you track players from more than one level.

## Coach's Corner and goals

- **Coach's Corner** (`backend/app/insights.py`) flags stats where recent form has moved past a
  threshold from the season, e.g. walk rate up or fastball velocity down, and pairs each with a
  concrete thing to work on, or to keep doing when the trend is good. It also suggests pitch-mix
  changes (an underused pitch with the best whiff rate) and explains luck (high BABIP, ERA far
  from FIP). Add a rule by adding an entry to `TREND_RULES`.
- **Goals:** set a target for any stat with a direction (e.g. BB/9 ≤ 3.0). Each goal shows
  **Met**, **On track** (recent form is at the target or moving toward it), or **Off track**.

Insights are heuristics to start a conversation with a coach. A velocity drop in particular is
worth checking with an athletic trainer.

## Using PostgreSQL

The backend reads `DATABASE_URL`, and falls back to `sqlite:///./pitchlab.db` when it isn't set.

```bash
docker compose up -d            # Postgres 16 on :5432
set DATABASE_URL=postgresql+psycopg://pitchlab:pitchlab@localhost:5432/pitchlab
python -m app.seed
uvicorn app.main:app --reload
```

(PowerShell: `$env:DATABASE_URL="postgresql+psycopg://..."`.) You can also skip Docker and
install Postgres directly.

## Real data and accuracy

Every pitcher records where its numbers came from, and the UI always says so:

| Source | Box scores | Pitch data | Label in the app |
|---|---|---|---|
| `mlb` | MLB Stats API: the official scorer's line, every level from Single-A to MLB | Statcast (MLB games) | ✓ Official MLB data, or ⚠ if it fails the check |
| `csv` | Counted from the pitch events in your upload (all runs treated as earned) | Your file | ↑ Uploaded CSV |
| `manual` | Typed in from a scorebook | none | ✎ Entered by hand |
| `simulated` | Generated by `seed.py` | Generated | ◇ Simulated data |

**Syncing real pitchers** (public league data):

```bash
python -m app.sync_mlb "Tarik Skubal" --season 2024
python -m app.sync_mlb --id 694973 --season 2024     # by MLB id when a name is ambiguous
python -m app.sync_mlb --refresh                     # re-sync everyone, e.g. nightly
```

How a sync stays accurate:

- **Each stat comes from the source that owns it.** Earned runs, innings and decisions come from
  the official game log, never from pitch events (Statcast doesn't know which runs were earned).
- **Players are matched by MLB id, games by `game_pk`,** never by name or date, so two players
  with the same name stay separate, doubleheaders stay separate, and re-syncing changes nothing
  that hasn't changed.
- **Every sync is checked.** `reconcile` adds up the stored games and compares them with MLB's
  official season line at each level (G, IP, H, R, ER, BB, K, HR, HBP, BF, ERA), plus Statcast
  pitches against the official pitch count. Pitch-clock violations are left out, because Statcast
  logs them but no pitch was thrown. The result is saved with the pitcher and shown on their
  page. A mismatch shows a warning, so it can't go unnoticed.
- **Headline stats use one level.** A season split across levels (Skenes: AAA, then MLB) shows the
  current level's line, matching how MLB reports it; every level is listed on the player page.
- **Tested against a real season.** `tests/test_sync_mlb.py` replays recorded MLB responses for
  Skubal's 2024 Cy Young season and checks it to the decimal (2.39 ERA, 192.0 IP, 228 K, 2,866
  pitches). Re-record with `python -m tests.fixtures.record_mlb`.

**Coverage beyond pro ball:** there's no public, scrapeable source for college or high-school
pitching (stats.ncaa.org and MaxPreps don't allow scraping, and TrackMan data belongs to each
school), or for the transfer portal. For those levels, coaches enter games by hand or upload a
CSV exported from their own TrackMan/Rapsodo, and the label says so.

**Uploading a Statcast CSV yourself:** download one from
[Baseball Savant](https://baseballsavant.mlb.com/statcast_search) and upload it from your dugout,
or `curl -F file=@savant.csv localhost:8000/api/ingest/statcast`. Box scores are derived from the
pitch events, so prefer `sync_mlb` for MLB pitchers.

**Your own bullpens:** fill in `sample_data/my_bullpen_template.csv` (velo from a radar gun,
spin from a Rapsodo/TrackMan if you have one, location as feet from the center of the plate)
and upload it.

**Terms:** MLB data is free for personal, non-commercial use
([MLB terms](http://gdx.mlb.com/components/copyright.txt)). Don't charge for it or republish it
in bulk.

## Adding pitchers and games

- **+ Add pitcher** (My Dugout) creates a private profile with a photo, hometown, team, throwing
  hand and role. **Edit profile** on the player page changes any of it.
- **+ Add game** (game log) enters a box-score line by hand: IP as `6.2`, then H/R/ER/BB/K/HR/HBP.
  Batters faced is estimated if you leave it blank. Manual games feed every traditional stat;
  the pitch-level charts need CSV data.

## Adding a stat

Every stat lives in one list, `STATS` in `backend/app/analytics.py`. Add a line and it shows up in
`GET /api/stats`, in every pitcher's `stats`, and in the **Customize stats** picker:

```python
Stat("so_per_bf", "K/BF", "traditional",
     lambda t: rate(t["strikeouts"], t["batters_faced"]), 3,
     description="Strikeouts per batter faced", better="higher"),
```

`better="higher"` or `"lower"` turns on trend arrows and lets people set goals on the stat.

The formula receives a `totals` dict with the box-score sums and the pitch counters (the list is in
the module docstring). A stat that needs a new pitch-level count, such as first-pitch strikes,
needs one more line in `pitch_counters()` as well. `digits` and `suffix` control the display, and
`default=True` puts the stat on the dashboard until a viewer customizes their tiles.

## API

🔒 = requires sign-in. Write endpoints on a pitcher also require that you own it.

| Method | Path | |
|---|---|---|
| POST | `/api/auth/signup`, `/api/auth/login`, `/api/auth/logout` | account and session cookie |
| GET / DELETE | `/api/auth/me` | current user (or null) / delete account and everything it owns 🔒 |
| GET | `/api/me/dashboard` | tracked pitchers with season + recent stats, top insight, goals 🔒 |
| PUT / DELETE | `/api/me/tracked/{id}` | add to / remove from your dugout 🔒 |
| PUT | `/api/me/preferences` | which stats to show (`{"tiles": [...]}`) 🔒 |
| GET | `/api/pitchers/{id}/insights` | Coach's Corner |
| GET / POST | `/api/pitchers/{id}/goals` | your goals for a pitcher 🔒 |
| DELETE | `/api/goals/{id}` | remove a goal 🔒 |
| GET | `/api/pitchers` | league pitchers + yours, with ERA / K/9 / WHIP / FB velo. Filter with `?level=AAA&level=AA` or `?portal=true` |
| GET | `/api/stats` | every stat's label, group, formatting and description |
| POST | `/api/pitchers` | create a private pitcher (`name`, `team`, `throws`, `role`, `hometown`) 🔒 |
| PATCH | `/api/pitchers/{id}` | update any profile field |
| DELETE | `/api/pitchers/{id}` | delete a pitcher and all their data |
| POST / DELETE | `/api/pitchers/{id}/photo` | upload (JPEG/PNG/WebP/GIF, 5 MB) / remove photo |
| GET | `/api/pitchers/{id}` | bio + season stats + recent-form stats |
| GET | `/api/pitchers/{id}/arsenal` | per-pitch usage, velo, spin, zone/whiff/chase/CSW% |
| GET | `/api/pitchers/{id}/trend` | per-game avg velo & spin by pitch type |
| GET | `/api/pitchers/{id}/games` | game log |
| POST | `/api/pitchers/{id}/games` | enter a box-score line by hand |
| DELETE | `/api/pitchers/{id}/games/{game_id}` | delete a game |
| GET | `/api/pitchers/{id}/pitches` | raw pitches (`?pitch_type=SL&appearance_id=12`) |
| POST | `/api/ingest/statcast` | upload a Statcast-format CSV (pitchers become yours) 🔒 |

## Stat definitions

- **Zone%**: pitches with |plate_x| ≤ 0.83 ft and 1.5 ≤ plate_z ≤ 3.5 ft (a fixed zone; Statcast's
  per-batter `sz_top`/`sz_bot` would be more accurate)
- **Whiff%**: swinging strikes / swings · **Chase%**: swings on pitches outside the zone / pitches outside the zone
- **CSW%**: (called + swinging strikes) / pitches
- **FIP**: (13·HR + 3·(BB+HBP) − 2·K) / IP + 3.10

## Ideas for next steps

- Alembic migrations (startup currently creates tables and adds new nullable columns). This
  would also allow two same-named players in one account without the "(id)" suffix
- Seasons as a first-class concept (a synced pitcher holds one season at a time today)
- "Add from MLB" search in the UI, plus a scheduled `--refresh` job once deployed
- Statcast minor-league pitch data (Savant covers AAA and the Florida State League)
- Photo storage in S3 or similar for deployment (photos are saved in `backend/uploads/`)
- Movement data (`pfx_x`, `pfx_z`) and a movement chart
- Per-batter zones from `sz_top` / `sz_bot`
- Splits vs LHH/RHH, by count, by times through the order
- Login rate limiting, password reset and email verification before putting this online
- Sharing a dugout with teammates or a coach (read-only links or team accounts)
