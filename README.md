# pitch-dataset

Complete pitch-level **MLB** and **MiLB** Statcast data for insights, dashboards, and player evaluations — plus a **Pitch Arsenal Optimization** model that answers: *Is this pitcher using his pitches optimally?*

**Default season: 2026** (first-class). Pulls come from Baseball Savant CSV endpoints and land as Parquet under `data/`.

## View the visual

Open the static arsenal optimization summary (Cease headline + top-3 ΔxwOBA):

- **In a clone:** open [`reports/arsenal_optimization.html`](reports/arsenal_optimization.html) in your browser (double-click or `open reports/arsenal_optimization.html` on macOS).
- **Traded deadline:** [`reports/traded_pitchers.html`](reports/traded_pitchers.html) — Skubal, Gausman, Soriano, Mize, Peralta pre/post splits.
- **On GitHub:** [blob view](https://github.com/gdevers/pitch-dataset/blob/main/reports/arsenal_optimization.html) shows source; GitHub’s HTML preview does **not** run the page JS well. Prefer local open, or GitHub Pages if enabled for this private repo (Pro/Team required for private Pages).

Also listed under [`reports/`](reports/README.md).

## Layout (portfolio-friendly)

| Path | Role |
| --- | --- |
| `notebooks/arsenal_optimization.ipynb` | **Start here** — hiring walkthrough: data → features → outcome model → optimize → example recommendations |
| `src/pitch_dataset/arsenal.py` | All arsenal logic in one module (features, model, optimize, report) |
| `src/pitch_dataset/cli.py` | `pull` / `sample` / `train-model` / `optimize` / `traded` |
| `src/pitch_dataset/traded_analysis.py` | Pre/post trade-deadline usage, shape, pairing/tunnel reports |
| `reports/arsenal_optimization.html` | **Interactive visual** — open in a browser |
| `reports/` | Example markdown recommendations (e.g. Cease) |
| `models/outcome_model.joblib` | Trained demo artifact |

Dataset plumbing (`pipeline`, `savant`, `storage`, `seasons`) stays separate from the arsenal story.

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

# Explicit season-to-date window (same as default clamp-to-today)
uv run pitch-dataset pull --league mlb --season 2026 --start 2026-03-20 --end 2026-08-14

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

Context includes platoon (`p_throws`/`stand`), count, zone/location, times-through-order, previous pitch (sequencing), batter prior xwOBA, and **extended pitch-shape + pairing** signals — not a separate product.

**Shape features (pitch-level, per Statcast pitch):** `arm_angle`, `release_spin_rate`, `spin_axis`, `release_extension`, `effective_speed`, `release_pos_y`, `api_break_x_arm`, `api_break_x_batter_in`, `api_break_z_with_gravity`.

**Pairing features (pitcher-level vs primary pitch):** velo/movement separation (existing), plus effective-speed, arm-angle, extension, spin-rate, spin-axis (circular), API-break (3D), and 3D release similarity (`release_pos_x/y/z`). Nulls are median-imputed at train/score time (~98% fill on arm angle; spin/break ~99.5%).

During optimization, candidate pitch types get their pitcher-specific shape means and pairing separations (not the thrown pitch’s raw values).

### Demo data window

The committed example reports and `models/outcome_model.joblib` were trained on:

- **League:** MLB
- **Dates:** 2026-03-25 → 2026-08-13 (season-to-date; pull window 2026-03-20 → 2026-08-14)
- **Sample size:** 491,230 pitches (~489k after pitch-type filters used in training)

Parquet files stay gitignored under `data/`. Re-pull the season-to-date window to reproduce locally.

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
| Features | Platoon, count buckets, zone/plate location, TTO, runners, score state, batter prior, prev pitch, **9 pitch-shape Statcast fields**, **9 pairing separations** (velo/move/spin/arm/extension/break/release), pitch-type one-hots |
| Optimization | Per pitcher × platoon (and count) segment: SLSQP mix minimizing expected xwOBA under usage constraints |
| Constraints | Established pitches (≥5%): ±`max_shift` (default 15 pts), floors/caps (`min_pct`/`max_pct`); fringe pitches held fixed |

### Limitations

- Season-to-date samples are still noisy; treat deltas as directional, not precise WAR.
- Holds **location** and game state fixed — only reallocates pitch-type share.
- Pitch-level xwOBA for takes/whiffs is a heuristic mapping; BIP uses Savant `estimated_woba_using_speedangle` when present.
- No explicit game-planning, catcher, or health constraints.
- Pairing/tunnel metrics are descriptive features (extended with spin, arm angle, extension, API break), not a full tunneling model.

### Traded deadline analysis

Pre/post splits for headline deadline arms (usage mix, Statcast shape, pairing/tunnel):

```bash
# Default top-5: Skubal, Gausman, Soriano, Mize, Peralta
uv run pitch-dataset traded

# Subset by key or last name
uv run pitch-dataset traded --pitchers skubal,gausman --report reports/traded_pitchers.md --html reports/traded_pitchers.html
```

Outputs: `reports/traded_pitchers.md`, `reports/traded_pitchers.html`. Team affiliation is derived from `inning_topbot` + home/away; post-trade samples are partial through the data end date.

### Example output

Interactive visual: [`reports/arsenal_optimization.html`](reports/arsenal_optimization.html). Write-up: `reports/example_cease.md`. Excerpt:

```text
## Cease, Dylan (MLBAM 656302)
- Overall expected xwOBA: 0.283 → 0.279 (improvement -0.004)

#### vs LHH
- INCREASE SL usage from 24% → 39%
- INCREASE KC usage from 12% → 27%
Expected improvement: -0.003 xwOBA
```

### Notebook (recommended read order)

```bash
uv run jupyter notebook notebooks/arsenal_optimization.ipynb
```

Walkthrough: load pitches → build features → train/load outcome model → optimize one pitcher → print recommendations.

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
from pitch_dataset.arsenal import (
    load_outcome_model,
    optimize_pitcher,
    format_recommendation_report,
)
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
