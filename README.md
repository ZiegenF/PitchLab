# PitchLab

A full-stack pitching analytics app: ingest pitch-by-pitch data, compute traditional and
pitch-level stats, and visualize them.

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
python -m app.seed              # mock 2026 season (6 pitchers, ~15k pitches) + a demo account
uvicorn app.main:app --reload
```

**Frontend** (http://localhost:5173; `/api` is proxied to the backend):

```bash
cd frontend
npm install
npm run dev
```

**Tests:** `cd backend && pytest`

**Demo account** (created by the seed): `demo@pitchlab.dev` / `pitchlab-demo`. It tracks three
league pitchers plus one private pitcher of its own, with goals set, so every feature has data.

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

## Loading real data

1. Go to [Baseball Savant Statcast Search](https://baseballsavant.mlb.com/statcast_search), pick
   a pitcher and date range, and click **Download CSV**.
2. Upload it in the sidebar, or with `curl -F file=@savant.csv localhost:8000/api/ingest/statcast`.

Box-score lines (IP, H, BB, K, HR, R) are derived from the `events` and score columns. Statcast
has no earned/unearned split, so every run is counted as earned.

**Your own bullpens:** fill in `sample_data/my_bullpen_template.csv` (velo from a radar gun,
spin from a Rapsodo/TrackMan if you have one, location as feet from the center of the plate)
and upload it.

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

- Alembic migrations (startup currently creates tables and adds new nullable columns)
- Photo storage in S3 or similar for deployment (photos are saved in `backend/uploads/`)
- Movement data (`pfx_x`, `pfx_z`) and a movement chart
- Per-batter zones from `sz_top` / `sz_bot`
- Splits vs LHH/RHH, by count, by times through the order
- Login rate limiting, password reset and email verification before putting this online
- Sharing a dugout with teammates or a coach (read-only links or team accounts)
