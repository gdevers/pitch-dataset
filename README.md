# pitch-dataset

Complete pitch-level **MLB** and **MiLB** Statcast data for insights, dashboards, and player evaluations — plus a **Pitch Arsenal Optimization** model that answers: *Is this pitcher using his pitches optimally?*

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

# Custom range (what the demo model used)
uv run pitch-dataset pull --league mlb --season 2026 --start 2026-04-01 --end 2026-05-15

# Custom MiLB levels
uv run pitch-dataset pull --league minors --levels AAA,A
```

Outputs:

| File | Contents |
| --- | --- |
| `data/pitches_mlb_2026.parquet` | MLB Statcast pitches |
| `data/pitches_minors_2026.parquet` | MiLB Statcast pitches |

## Pitch arsenal optimization

### What it does

For each pitcher, the model:

1. Estimates **pitch value** (run value + approximate pitch-level xwOBA) given context and pitch choice.
2. Compares **actual usage** to a **constrained optimal mix** (keep existing arsenal pitches; min/max %; max shift from current).
3. Emits recommendations like: *Reduce SL vs LHH from 23% → 11%; increase CH to 35%; expected improvement: -0.004 xwOBA.*

Context includes platoon (`p_throws`/`stand`), count, zone/location, times-through-order, previous pitch (sequencing), batter prior xwOBA, and light **pitch-pairing** signals (velo separation, movement separation, release similarity / tunnel proxy) as features and report notes — not a separate product.

### Demo data window

The committed example reports and `models/outcome_model.joblib` were trained on:

- **League:** MLB
- **Dates:** 2026-04-01 → 2026-05-15
- **Sample size:** ~175,759 pitches (~175k after pitch-type filters)

Parquet files stay gitignored under `data/`. Re-pull the same window to reproduce locally.

### Train

```bash
uv run pitch-dataset train-model --league mlb --season 2026
# writes models/outcome_model.joblib
```

### Optimize

```bash
# By name or MLBAM id
uv run pitch-dataset optimize --pitcher "Cease"
uv run pitch-dataset optimize --pitcher 656302 --report reports/example_cease.md

# Top pitchers by volume (trains if model missing)
uv run pitch-dataset optimize --top 3 --train-if-missing --report reports/example_top3.md
```

### Method

| Piece | Approach |
| --- | --- |
| Outcome model | Dual `HistGradientBoostingRegressor` targets: `delta_run_exp` and constructed pitch xwOBA |
| Features | Platoon, count buckets, zone/plate location, TTO, runners, score state, batter prior, prev pitch, pairing metrics, pitch-type one-hots |
| Optimization | Per pitcher × platoon (and count) segment: SLSQP mix minimizing expected xwOBA under usage constraints |
| Constraints | Established pitches (≥5%): ±`max_shift` (default 15 pts), floors/caps (`min_pct`/`max_pct`); fringe pitches held fixed |

### Limitations

- Early-season samples are noisy; treat deltas as directional, not precise WAR.
- Holds **location** and game state fixed — only reallocates pitch-type share.
- Pitch-level xwOBA for takes/whiffs is a heuristic mapping; BIP uses Savant `estimated_woba_using_speedangle` when present.
- No explicit game-planning, catcher, or health constraints.
- Pairing/tunnel metrics are descriptive features, not a full tunneling model.

### Example output

See `reports/example_cease.md`. Excerpt:

```text
## Cease, Dylan (MLBAM 656302)
- Overall expected xwOBA: 0.289 → 0.283 (improvement -0.006)

#### vs LHH
- INCREASE CH usage from 20% → 35%
- REDUCE SL usage from 23% → 11%
Expected improvement: -0.004 xwOBA
```

### Notebook

```bash
uv run jupyter notebook notebooks/arsenal_optimization.ipynb
```

## Python API

```python
from pitch_dataset import DEFAULT_SEASON, pull_pitches, season_date_range

assert DEFAULT_SEASON == 2026
start, end = season_date_range(2026)

results = pull_pitches(season=2026, league="all")
mlb = results[0].frame
minors = results[1].frame
```

```python
from pitch_dataset.arsenal import load_outcome_model, optimize_pitcher, format_recommendation_report
from pitch_dataset.storage import read_pitches

pitches = read_pitches("data/pitches_mlb_2026.parquet")
model = load_outcome_model("models/outcome_model.joblib")
rec = optimize_pitcher(pitches, model, pitcher="Cease")
print(format_recommendation_report(rec))
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
