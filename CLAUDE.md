# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Project context

This is a Flask web app for tracking stats in a fantasy baseball league ("BU") built around the Cubs schedule. The current live website runs on PythonAnywhere with a MySQL database. The goal of this repository is to become the full replacement for that production setup.

Target migration outcome:

- Move the website off PythonAnywhere and run it from this project/deployment.
- Translate the existing MySQL data into Postgres.
- Validate that the nightly CBS scrape/import workflow works here.
- Refactor code where needed for Postgres, reliability, deployment, and new requirements.
- Point the live URL to the new deployment.
- Retire the PythonAnywhere app only after parity is proven.

Treat this project as an active migration, not a completed rewrite. Preserve live behavior while moving pieces over.

## Current production vs target state

### Current production

- Live host: PythonAnywhere.
- Live database: MySQL.
- Data source: CBS scrape/import workflow plus schedule data.
- Existing table and column names may reflect MySQL-era conventions and should not be renamed casually.

### Target state

- App runs from this repository/deployment.
- Database is Postgres via SQLAlchemy.
- `DATABASE_URL` should point at the active target database.
- Nightly scrape/import jobs should run outside PythonAnywhere and be observable/retryable.
- DNS cutover should happen only after data parity, route parity, and scrape parity are validated.

## Verifying data questions

When the user asks whether something happened — a cron job ran, stats loaded, data updated — **checking the log file is not sufficient**. Logs confirm the script ran and reported success; they do not confirm data actually landed. Always verify by querying the database directly:

```bash
sudo -u postgres psql -d bu2025 -c "
SELECT 'teamstat' as tbl, MAX(\"Date\") as latest, COUNT(*) as rows FROM teamstat
UNION ALL SELECT 'hitterstats', MAX(\"Date\"), COUNT(*) FROM hitterstats
UNION ALL SELECT 'pitcherstats', MAX(\"Date\"), COUNT(*) FROM pitcherstats
UNION ALL SELECT 'games', MAX(\"Date\"), COUNT(*) FROM games;
"
```

Report both the log output and the DB result to the user.

## Commands

All commands assume the virtualenv is active:

```bash
. .venv/bin/activate
```

Run the dev server:

```bash
python run.py
```

Run tests:

```bash
pytest tests/
```

Run a single test:

```bash
pytest tests/test_stats.py::TestCalcHittingStats::test_basic_calculation
```

Database migrations:

```bash
flask db migrate -m "description"
flask db upgrade
```

Load the Cubs schedule into the configured database:

```bash
python scripts/load_cubs_schedule.py
```

## Environment variables

Current checked-in config reads these variables:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask secret key. If missing, a random value is generated at startup. |
| `SEASON_YEAR` | Current season year, for example `2026`; date queries filter on this. |
| `DATABASE_URL` | SQLAlchemy database URL for the active database. Target state is Postgres. |

Historical PythonAnywhere/MySQL deployment details may still exist outside this repo. Do not assume the checked-in config fully captures current production until verified against PythonAnywhere.

## Migration priorities

Work in this order unless the user asks otherwise:

1. Preserve current live behavior.
2. Document current MySQL schema, row counts, and scrape outputs.
3. Create or verify the Postgres schema.
4. Migrate MySQL data to Postgres with explicit type handling.
5. Validate row counts and key aggregates between MySQL and Postgres.
6. Run the Flask app against Postgres.
7. Validate all routes against the migrated data.
8. Validate the CBS scrape/import workflow against Postgres.
9. Add tests around stat calculations, data transforms, and import behavior.
10. Prepare deployment, nightly scheduling, logs, backups, and rollback.
11. Cut over DNS only after parity checks pass.
12. Retire PythonAnywhere after the new site has run successfully for a safe observation window.

## Important migration cautions

- Do not remove MySQL/PythonAnywhere assumptions until the replacement path is proven.
- Do not rename historical tables or columns unless the migration includes compatibility handling.
- Be careful with MySQL-to-Postgres differences: identifier case, date handling, float/numeric behavior, reserved words, boolean coercion, and SQL functions.
- Raw SQL should be reviewed for Postgres compatibility.
- Keep `2B` and `3B` column mappings intact unless the schema is intentionally changed everywhere.
- Verify scraper output shape before refactoring import code.
- Any change to stat formulas should be treated as a business logic change and tested against known examples.

## Architecture notes

### Application structure

- App factory: `app/__init__.py`
- Routes: `app/routes/main.py`
- Models: `app/models/`
- Shared stat helpers: `app/services/stats.py`
- Chart generation: `app/services/charts.py`
- Templates: `app/templates/`
- Static assets: `app/static/`
- Scripts: `scripts/`
- Tests: `tests/`

### Database connection

Current `config.py` is simple:

- Loads `.env` with `python-dotenv`.
- Reads `SEASON_YEAR`.
- Reads `DATABASE_URL` into `SQLALCHEMY_DATABASE_URI`.
- Uses one `Config` class for development, production, and default.

There is currently a stale tunnel cleanup reference in `app/__init__.py`:

```python
if Config.tunnel:
    atexit.register(lambda: Config.tunnel.stop())
```

`Config.tunnel` is not defined in the current `config.py`. Fix this before relying on local startup.

### Data model pattern

Most tables use composite primary keys:

- Team-level tables: `(Date, BUTeam)`
- Player-level tables: `(Date, BUTeam, Player)`

There are no auto-incrementing IDs in the main stat models.

"Most recent date" is the freshness anchor. Routes query the latest `Date`, filtered to `SEASON_YEAR`, to decide what to display.

### Column naming

Database columns named `2B` and `3B` cannot be Python identifiers, so models map them as:

```python
_2B = db.Column('2B', db.Float)
_3B = db.Column('3B', db.Float)
```

Keep this in mind when migrating schema, writing raw SQL, or building pandas transforms.

### Team model

`Team` maps to `teamstat`.

(There is no `Standings` model. An earlier `Standings` view of `teamstat` was
removed; standings data is read directly from `Team`. Do not reintroduce a
`Standings` model without a clear need.)

### Cubs schedule model

`CubsSchedule` (`app/models/cubsschedule.py`) maps to the `cubsschedule` table
(`date`, `games`, `xfactor`, all lowercase). The home page and
`_get_season_start_date` query it through this model rather than raw SQL.

### "Yesterday" tables

`hitterstats_yest` and `pitcherstats_yest` are separate tables that mirror the main player stat tables for single-day data.

The `teamstatsyest` route does not use a separate yesterday table. It calculates day-over-day changes by comparing the two most recent dates in `teamstat`.

### Stat calculation

Raw stats are stored in the database. Derived stats are computed in Python:

- Hitters: `AVG`, `OBP`, `SLG`, `OPS`
- Pitchers: `BB9`, `K9`, `WHIP`

The helpers live in `app/services/stats.py`:

- `calc_hitting_stats()`
- `calc_pitching_stats()`
- `clean_player_name()`

These functions mutate the model object in place and return it for convenience.

`teamstatsyest` has additional inline delta math for ERA, OPS, and RC. Be careful when changing this because it is independent from the shared helpers.

### Charts

`app/services/charts.py` uses matplotlib with the `Agg` backend. It creates line charts with a rolling moving average and returns base64-encoded PNG data for embedding directly in HTML.

No chart files are written to disk.

### Cubs schedule table

Current route and loader code use the `cubsschedule` table.

`scripts/load_cubs_schedule.py` loads `CubsSchedule2026.xlsx`, drops and recreates `cubsschedule`, then inserts rows with:

- `date`
- `games`
- `xfactor`

The home page queries `xfactor` from `cubsschedule` for the most recent stat date.

### Qualifying thresholds

Defined in `app/routes/main.py`:

- Hitting leaders: `AB >= 2 * BUGames`
- Pitching leaders, season: `INN >= 0.617 * BUGames`
- Pitching leaders, yesterday: `INN >= 0.1`
- Player analysis moving average window: `7`

### Player name cleaning

Player names from source data may contain non-breaking spaces (`\xa0`). Use `clean_player_name()` before display when needed.

## CBS scrape/import workflow

The scrape workflow is part of the migration risk area. Before making major changes:

- Identify what `scripts/CBS_Scrape.py` currently reads, writes, and expects.
- Confirm whether it depends on cookies, browser state, local files, MySQL-specific SQL, or PythonAnywhere paths.
- Run it in a controlled mode before scheduling nightly execution.
- Compare generated rows against current production output.
- Add logging around scrape start, scrape completion, rows inserted/updated, and failures.

The file `scripts/cbs_cookies.json` exists in the repo. Treat cookies and credentials carefully; do not print secrets into logs or commit new secret material.

## Testing notes

`tests/test_stats.py` loads `app/services/stats.py` directly with `importlib`. This keeps stat helper tests independent from Flask app startup and database configuration.

When adding tests:

- Prefer pure unit tests for stat formulas and data transforms.
- Add integration tests only when a test database is clearly configured.
- Do not make tests depend on production MySQL, production Postgres, PythonAnywhere, or live CBS access.
- Use known fixed examples for migration parity checks.

## Deployment cutover checklist

Before pointing the live URL at the new deployment:

- App starts cleanly with the target environment.
- Postgres schema exists and migrations are reproducible.
- MySQL-to-Postgres migration has documented row-count checks.
- Key pages match production for the same `SEASON_YEAR` and latest date.
- Leaderboards and team pages match expected ordering and thresholds.
- Schedule `xfactor` data displays correctly.
- CBS scrape/import works against Postgres.
- Nightly job scheduling is configured and logs are accessible.
- Backups exist for Postgres.
- Rollback plan is documented.
- PythonAnywhere remains available until the new deployment has proven stable.

## Code style guidance

- Prefer small, behavior-preserving refactors during migration.
- Keep business formulas explicit and tested.
- Use SQLAlchemy where practical; when using raw SQL, make it Postgres-compatible.
- Avoid broad rewrites until database parity and scrape parity are established.
- Keep configuration explicit and environment-driven.
- Do not add new dependencies without updating `requirements.txt` and documenting why.
