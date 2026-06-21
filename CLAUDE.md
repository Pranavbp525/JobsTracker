# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Job Application Tracker — a web app for logging daily job applications, tracking
streaks/goals, and visualizing activity on a calendar (inspired by workout-logging
apps). Three Docker services: PostgreSQL, a Flask REST API, and an Nginx-served
static frontend.

## Running the app

The whole stack runs through Docker Compose from the repo root:

```bash
docker-compose up --build        # build + run all three services
docker-compose up --build -d     # detached
docker-compose down              # stop (add -v to also wipe the DB volume)
```

After startup:
- Frontend: http://localhost:8080
- Backend API: http://localhost:5001/api
- Postgres: localhost:5432

**Before first run** you must set a real DB password. The same password appears in
*two* places in `docker-compose.yml` and they must match: `POSTGRES_PASSWORD` (db
service) and the password inside `DATABASE_URL` (backend service). The README's
`your_strong_password` is a placeholder.

### Running the backend alone (without Docker)

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# create backend/.env with a real DATABASE_URL (see backend/.env template)
flask run --host=0.0.0.0 --port=5001
```

`database.py` raises at startup if `DATABASE_URL` is unset.

## Tests, lint, build

There is **no test suite, no linter, and no frontend build step** in this repo.
The frontend is a single hand-written HTML file loaded directly by Nginx; the
backend is plain Flask run via `flask run`. Don't look for or invent these
toolchains — if asked to add tests/CI, you're starting from scratch.

## Architecture

### Backend (`backend/`, Flask + SQLAlchemy)
- `app.py` — all REST endpoints (see list below) and the Flask app bootstrap.
  On startup it calls `db.create_all()` and seeds default settings.
- `models.py` — SQLAlchemy models plus the two core domain helpers
  `get_settings()` and `get_current_status()` (streak/stats calculation).
- `database.py` — `db` instance + `init_app()` wiring `DATABASE_URL`.
- `wait-for-db.sh` — Docker entrypoint that blocks on `nc -z db 5432` until
  Postgres accepts connections before launching `flask run`.

**Data model (3 tables):**
- `Setting` — single global row (`key='global_settings'`) holding `daily_goal`
  (default 5). Always accessed via `get_settings()`, which lazily creates it.
- `DailyLog` — one row per day. Primary key is `log_date` (a `Date`, *not* an
  int id). Holds `status` (`'complete'`/`'incomplete'`), `completed_count`,
  `elapsed_seconds`.
- `ApplicationLog` — individual applications, FK `log_date → daily_logs.log_date`.
  One-to-many from `DailyLog.applications` with `cascade="all, delete-orphan"`.

**Schema is created via `db.create_all()`, not migrations.** There is no Alembic
or migration tooling. Changing a model does not alter an existing table — you must
drop/recreate the table or the volume manually for schema changes to take effect.

### Frontend (`frontend/index.html`)
A single ~980-line file with embedded `<script>` (vanilla JS, no framework, no
bundler) and styling via Tailwind + Font Awesome **CDNs**. All state lives on the
backend — there is no localStorage. The API base is hardcoded near the top:

```js
const API_BASE_URL = 'http://localhost:5001/api';
```

Note the browser calls the backend on `:5001` directly (not proxied through
Nginx), which is why Flask-CORS is enabled. If the API host/port changes, update
this constant.

## Key conventions & gotchas

- **Eastern Time is the source of truth for "today".** `get_eastern_today()` in
  `app.py` and the timezone logic in `models.get_current_status()` both use
  `America/New_York` (via `zoneinfo`, falling back to `pytz`). Use these helpers
  rather than `date.today()` when determining the current day — `date.today()`
  would use the container's local time and break streak logic. (`get_eastern_today()`
  now lives in `models.py` and is shared by `app.py`; `/api/debug_streaks` uses it too.)
- **Two distinct streaks.** `totalStreak` = consecutive recent days with *any*
  finished log; `goalStreak` = consecutive recent days with `status='complete'`.
  Both are computed by walking backward from today in `get_current_status()`.
- **`finish_day` is an upsert that replaces applications.** It updates-or-inserts
  the `DailyLog` for today, then *deletes all existing `ApplicationLog`s for that
  date and re-inserts* the submitted list. This is how "Continue Logging" works —
  the frontend resends the full list each time.
- **`reset` deletes in FK-safe order**: `ApplicationLog` → `DailyLog` → `Setting`,
  then re-seeds default settings.
- API request/response keys are camelCase on the wire (`jobName`, `completedCount`,
  `dailyGoal`), mapped to snake_case columns in `models.py` / `to_dict()`.

## API endpoints (all under `/api`)

- `GET /health` — liveness/readiness probe (checks DB reachability)
- `GET /state` — current goal + streaks/status (now also `currentMilestone`, `nextMilestone`)
- `PUT /goal` — update daily goal (`{"goal": int}`); records a `GoalHistory` row on change
- `GET /goal_history` — chronological list of goal changes
- `GET /session/<YYYY-MM-DD>` — a day's log + applications (used to resume)
- `POST /finish_day` — finish/log today (`completedCount`, `elapsedSeconds`, `applications[]`, optional `notes`)
- `GET /calendar_data?month=&year=` — per-day statuses for a month (now includes `completedCount`)
- `GET /logs/<YYYY-MM-DD>` — applications + notes logged on a date
- `PUT /logs/<YYYY-MM-DD>` — edit a past day (count/elapsed/notes/applications); status recomputed vs current goal
- `DELETE /logs/<YYYY-MM-DD>` — delete one day's log (cascades to its applications)
- `GET /analytics` — aggregate stats (totals, averages, completion rate, best day, longest streak, per-weekday)
- `GET /export_logs?format=csv|json` — export all logs (now includes `notes`)
- `GET /server_time` — current Eastern time
- `DELETE /reset` — wipe all data (now also clears `GoalHistory`)
- `GET /debug_streaks` — debug dump of logs + computed streaks (now uses the Eastern helper)

### Schema additions (require a fresh DB / volume reset)
The schema is created via `db.create_all()` with **no migration tooling**, so new
columns/tables only materialize on an empty database. The additive changes below
are backward-tolerant (nullable / new table) but won't appear on an existing
volume until you `docker-compose down -v` (wipes the DB) and bring the stack back up:
- `DailyLog.notes` (nullable `Text`) — optional per-day note.
- `GoalHistory` table — records each daily-goal change.

### Tests
A lightweight, optional test suite lives in `backend/tests/` and runs against an
in-memory SQLite DB (no Postgres needed). It is **not** part of any build step:
```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest
```
