# pitch-dataset

Complete pitch-level **MLB** and **MiLB** Statcast data for insights, dashboards, and player evaluations.

**Default season: 2026** (first-class). Pulls come from Baseball Savant CSV endpoints and land as Parquet under `data/`.

## Setup

Requires [uv](https://docs.astral.sh/uv/) (ships its own Python — no Xcode CLT needed):

```bash
cd ~/Projects/pitch-dataset
uv sync --extra dev
```

## Quick start

Smoke-test a single **2026** day for both leagues:

```bash
uv run pitch-dataset sample
# or pick a day:
uv run pitch-dataset sample --date 2026-04-15
```

Pull the full season-to-date window (2026 calendar start → today):

```bash
uv run pitch-dataset pull
```

Useful variants:

```bash
# MLB only, 2026
uv run pitch-dataset pull --league mlb --season 2026

# Minors only (AAA + A by default)
uv run pitch-dataset pull --league minors --season 2026

# Custom range
uv run pitch-dataset pull --season 2026 --start 2026-04-01 --end 2026-04-07

# Custom MiLB levels
uv run pitch-dataset pull --league minors --levels AAA,A
```

Outputs:

| File | Contents |
| --- | --- |
| `data/pitches_mlb_2026.parquet` | MLB Statcast pitches |
| `data/pitches_minors_2026.parquet` | MiLB Statcast pitches |

## Python API

```python
from pitch_dataset import DEFAULT_SEASON, pull_pitches, season_date_range

assert DEFAULT_SEASON == 2026
start, end = season_date_range(2026)

results = pull_pitches(season=2026, league="all")
mlb = results[0].frame
minors = results[1].frame
```

## Coverage notes

- **MLB**: pitch-level Statcast via Savant `statcast_search/csv`.
- **Minors**: Savant `statcast-search-minors/csv`. Tracking coverage is strongest for **AAA** and **A** (Savant’s documented levels); other levels may be sparse or empty.
- Requests are chunked by day to stay under Savant’s CSV size limits.
- Season end dates clamp to today so in-season refreshes stay current.

## Explore

```bash
uv run jupyter notebook notebooks/explore_pitches.ipynb
```

## Schema

Columns match Baseball Savant’s Statcast Search CSV export, plus:

- `league` — `mlb` or `minors`
- `season` — season year (defaults to **2026**)

See [Savant CSV docs](https://baseballsavant.mlb.com/csv-docs/) for field definitions.
