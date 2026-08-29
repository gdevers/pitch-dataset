# pitch-dataset

Complete pitch-level **MLB** and **MiLB** Statcast data for insights, dashboards, and player evaluations — plus a **Pitch Arsenal Optimization** model that answers: *Is this pitcher using his pitches optimally?*

**Default season: 2026** (first-class). Pulls come from Baseball Savant CSV endpoints and land as Parquet under `data/`.

## View the visual

Open the static arsenal optimization summary (Cease headline + top-3 ΔxwOBA):

- **In a clone:** open [`reports/arsenal_optimization.html`](reports/arsenal_optimization.html) in your browser (double-click or `open reports/arsenal_optimization.html` on macOS).
- **Traded deadline:** [`reports/traded_pitchers.html`](reports/traded_pitchers.html) — Skubal, Gausman, Soriano, Mize, Peralta pre/post splits.
- **Shape & pairing lab:** [`reports/traded_pitchers_shape.html`](reports/traded_pitchers_shape.html) — arm angle, spin, extension, effective speed, API break, extended pairing/tunnel (pitcher switcher). Canvas: [`traded-pitchers-shape.canvas.tsx`](/Users/grantdevers/.cursor/projects/Users-grantdevers-Projects-pitch-dataset/canvases/traded-pitchers-shape.canvas.tsx).
- **Situational selection (live demo):** [**gdevers.github.io/pitch-dataset/**](https://gdevers.github.io/pitch-dataset/) — interactive pitch-choice game cards (8×8 demo grid). Local copy: [`reports/situational_selection.html`](reports/situational_selection.html). Full roster + live inference: `uv run pitch-dataset select-web`. Canvas: [`situational-selection.canvas.tsx`](/Users/grantdevers/.cursor/projects/Users-grantdevers-Projects-pitch-dataset/canvases/situational-selection.canvas.tsx).
- **On GitHub:** [blob view](https://github.com/gdevers/pitch-dataset/blob/main/reports/arsenal_optimization.html) shows source; GitHub’s HTML preview does **not** run the page JS well. Prefer the live Pages demo above or local open.

Also listed under [`reports/`](reports/README.md).

## Layout (portfolio-friendly)

| Path | Role |
| --- | --- |
| `notebooks/arsenal_optimization.ipynb` | **Start here** — hiring walkthrough: data → features → outcome model → optimize → example recommendations |
| `src/pitch_dataset/arsenal.py` | All arsenal logic in one module (features, model, optimize, report) |
| `src/pitch_dataset/situational.py` | Micro pitch-choice engine (context + pitch type → xwOBA; `recommend_pitch`) |
| `src/pitch_dataset/situational_web.py` | Local FastAPI server + static UI for full-roster live pitch selection |
| `src/pitch_dataset/cli.py` | `pull` / `pull-api` / `pull-fangraphs` / `pull-register` / `pull-all` / `sample` / `train-model` / `train-select` / `optimize` / `select` / `select-web` / `traded` |
| `src/pitch_dataset/mlb_api.py` | MLB Stats API schedules, rosters, transactions, lineups |
| `src/pitch_dataset/fangraphs.py` | FanGraphs leaderboards and platoon splits |
| `src/pitch_dataset/chadwick.py` | Chadwick player ID register |
| `src/pitch_dataset/joins.py` | Join Savant MLBAM ids → FanGraphs via Chadwick |
| `src/pitch_dataset/traded_analysis.py` | Pre/post trade-deadline usage, shape, pairing/tunnel reports |
| `reports/arsenal_optimization.html` | **Interactive visual** — open in a browser |
| `reports/` | Example markdown recommendations (e.g. Cease) |
| `models/outcome_model.joblib` | Trained demo artifact (arsenal optimization) |
| `models/situational_model.joblib` | Trained situational pitch-selection model |

Dataset plumbing (`pipeline`, `savant`, `storage`, `seasons`) stays separate from the arsenal story.

## Data inventory

All Parquet files live under `data/` (gitignored). Refresh commands below.

| Source | File(s) | Key columns | Refresh |
| --- | --- | --- | --- |
| **Baseball Savant** (pitch-level Statcast) | `pitches_mlb_{season}.parquet`, `pitches_minors_{season}.parquet` | `game_pk`, `pitcher`, `batter`, `pitch_type`, `release_speed`, shape fields, `estimated_woba_using_speedangle`, … | `uv run pitch-dataset pull --season 2026` |
| **MLB Stats API** (schedules) | `mlb_games_{season}.parquet` | `game_pk`, `game_date`, `home_team_id`, `away_team_id`, `status`, scores, venue | `uv run pitch-dataset pull-api --season 2026` |
| **MLB Stats API** (40-man rosters) | `mlb_rosters_{season}.parquet` | `team_id`, `player_id`, `position_code`, `status_code` | same |
| **MLB Stats API** (transactions) | `mlb_transactions_{season}.parquet` | `date`, `type_desc`, `player_id`, `team_id`, `from_team_id` | same |
| **MLB Stats API** (lineups) | `mlb_lineups_{season}.parquet` | `game_pk`, `player_id`, `batting_order`, `position_code`, `is_starter` | same (omit `--skip-lineups`; slower) |
| **FanGraphs** (season stats) | `fangraphs_batting_{season}.parquet`, `fangraphs_pitching_{season}.parquet` | `IDfg`, `xMLBAMID`, `player_name`, `WAR`, `wOBA`, `FIP`, … | `uv run pitch-dataset pull-fangraphs --season 2026` |
| **FanGraphs** (platoon splits) | `fangraphs_batting_splits_{season}.parquet`, `fangraphs_pitching_splits_{season}.parquet` | `IDfg`, `wOBA_vs_l` / `wOBA_vs_r`, `FIP_vs_l` / `FIP_vs_r`, … | same (omit `--skip-splits`) |
| **Chadwick register** (ID crosswalk) | `chadwick_register.parquet` | `key_mlbam`, `key_fangraphs`, `key_bbref`, `name_last`, `name_first` | `uv run pitch-dataset pull-register` |

**Unified refresh** (Savant + API + FanGraphs + Chadwick):

```bash
uv run pitch-dataset pull-all --season 2026
# Savant-only variant: add --skip-savant to refresh API/FG/register without re-pulling pitches
```

Savant vs API: Savant is pitch-level tracking (Statcast); the MLB Stats API adds game context (schedule, lineups, bullpen availability via rosters), transactions, and roster status — not pitch physics.

### Local pitch files (last updated 2026-08-28)

| File | League | Season | Date range | Pitches | Size |
| --- | --- | --- | --- | ---: | ---: |
| `pitches_mlb_2026.parquet` | MLB | 2026 | 2026-03-25 → 2026-08-27 | 593,334 | ~83 MB |
| `pitches_mlb_2025.parquet` | MLB | 2025 | 2025-03-18 → 2025-11-01 | 726,773 | ~107 MB |
| `pitches_minors_2026.parquet` | MiLB (AAA, A) | 2026 | 2026-03-27 → 2026-08-27 | 738,388 | ~85 MB |

**Pitch Statcast total:** 2,058,495 pitches. MiLB is strongest at AAA/A tracked parks; re-pull failed windows with `--start` / `--end` if Savant times out.

```bash
# Refresh current MLB season
uv run pitch-dataset pull --league mlb --season 2026

# Full prior MLB season
uv run pitch-dataset pull --league mlb --season 2025

# MiLB season-to-date (AAA + A default)
uv run pitch-dataset pull --league minors --season 2026

# Retry a failed MiLB window
uv run pitch-dataset pull --league minors --season 2026 --start 2026-05-08 --end 2026-05-11
```

### Joining Savant ↔ FanGraphs

Savant `pitcher` / `batter` columns are **MLBAM** ids. FanGraphs leaderboards expose `IDfg` and often `xMLBAMID`. Chadwick `key_mlbam` ↔ `key_fangraphs` is the canonical crosswalk when `xMLBAMID` is missing.

```python
from pitch_dataset.joins import join_pitches_to_fangraphs, load_join_bundle
from pitch_dataset.storage import read_parquet, chadwick_register_path

bundle = load_join_bundle("data", season=2026)
pitches_with_fg = join_pitches_to_fangraphs(
    bundle["pitches"],
    register=bundle["register"],
    fangraphs_pitching=bundle["fangraphs_pitching"],
    role="pitcher",
)

# Manual join (same keys):
register = read_parquet(chadwick_register_path("data"))
pitches = bundle["pitches"]
linked = pitches.merge(
    register[["key_mlbam", "key_fangraphs", "name_last", "name_first"]],
    left_on="pitcher",
    right_on="key_mlbam",
    how="left",
)
fg = bundle["fangraphs_pitching"][["IDfg", "WAR", "FIP", "wOBA"]]
linked = linked.merge(fg, left_on="key_fangraphs", right_on="IDfg", how="left")
```

### What this unlocks

| Model / analysis | Data used |
| --- | --- |
| **Bullpen availability** | `mlb_rosters_*` status + `mlb_transactions_*` IL/dfa moves |
| **Lineup-aware matchups** | `mlb_lineups_*` batting order + Savant platoon (`p_throws`/`stand`) + FG platoon splits |
| **Transaction impact** | `mlb_transactions_*` joined to Savant pre/post via `player_id` |
| **WAR / value overlays** | FanGraphs `WAR`, `FIP`, `wOBA` on pitch-level or pitcher rollup via Chadwick |
| **Cross-source player cards** | Chadwick links MLBAM ↔ FanGraphs ↔ BBRef for unified profiles |

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

Pull MLB API, FanGraphs, and Chadwick register:

```bash
uv run pitch-dataset pull-api --season 2026
uv run pitch-dataset pull-fangraphs --season 2026
uv run pitch-dataset pull-register

# Or everything at once (Savant + API + FanGraphs + Chadwick):
uv run pitch-dataset pull-all --season 2026
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
| `data/pitches_mlb_{season}.parquet` | MLB Statcast pitches |
| `data/pitches_minors_{season}.parquet` | MiLB Statcast pitches (AAA + A by default) |

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
- **Dates:** 2026-03-25 → 2026-08-27 (season-to-date; pull through 2026-08-28)
- **Sample size:** ~593k pitches locally (re-pull to refresh; model artifact may lag)

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

## Situational pitch selection

### What it does (vs `optimize`)

| | **`optimize`** | **`select`** |
| --- | --- | --- |
| Question | Is this pitcher using his pitches optimally over the season? | Against *this* batter, in *this* count, right now — which pitch minimizes damage? |
| Output | Reallocate pitch-type **usage %** (e.g. SL 24% → 39%) | Pick **one pitch** from the arsenal for this moment |
| Location | Holds zone/plate fixed | Excludes zone/plate (unknown pre-throw) |
| Extra context | Season segments (platoon, count buckets) | Leverage proxy, FanGraphs batter platoon splits, explicit game state |

Example:

```text
Cease vs Devers | LHH | 1-2 | high leverage
Recommended: FF (not SL)
  FF: pred xwOBA 0.253  ← pick
  SL: pred xwOBA 0.281
  ...
Expected improvement vs default: −0.028 xwOBA
```

### Train

```bash
uv run pitch-dataset train-select --league mlb --season 2026
# writes models/situational_model.joblib (~591k MLB 2026 pitches)
# optional multi-season: --seasons 2025,2026
```

### Select

```bash
uv run pitch-dataset select --pitcher "Cease" --batter "Devers" --count 1-2 \
  --leverage high --stand L --p-throws R --outs 2 --runners-on 1 --prev-pitch FF \
  --report reports/example_select_cease_devers.md

# Demo matchups + HTML game card (7 demo pitchers × 7 batters, precomputed grid)
uv run pitch-dataset select --demo
# -> reports/situational_selection.md, reports/situational_selection.html

# Full roster + live model inference (local web server)
uv run pitch-dataset train-select --league mlb --season 2026   # prerequisite
uv run pitch-dataset select-web
# -> http://127.0.0.1:8765/  (all pitchers/batters from pitches_mlb_2026.parquet)
```

### Method

| Piece | Approach |
| --- | --- |
| Outcome model | Dual `HistGradientBoostingRegressor` (same architecture as arsenal); **no zone/location** features |
| Context | Count, platoon, TTO, runners, score, outs, leverage proxy, prev pitch, batter prior xwOBA, FanGraphs platoon wOBA/xwOBA, pitch shape + pairing |
| Scoring | One feature row per arsenal pitch; rank by predicted xwOBA; compare best vs count/platoon **default** (pitcher's modal pitch in situation) |
| Training sample | MLB 2026: **591,030** pitches (2026-03-25 → 2026-08-27); combine with `--seasons 2025,2026` for ~1.3M |

### Limitations

- Pitch-level xwOBA is a heuristic mapping (same as arsenal model); R² is low — treat as directional.
- Leverage is a simple proxy (inning + score + runners), not full WPA/LI.
- Default pitch = modal type in count/platoon, not full game-plan or catcher preference.
- Small matchup samples (e.g. Cease vs Devers n=15) rely on model + batter priors, not head-to-head history alone.

**Two interactive UIs:**

| UI | Command | Scope |
| --- | --- | --- |
| **Demo HTML** (static, no server) | `uv run pitch-dataset select --demo` | 7 demo pitchers × 7 batters; 3,500+ precomputed recommendations. Open [`reports/situational_selection.html`](reports/situational_selection.html) in a browser. |
| **Full roster web app** (live inference) | `uv run pitch-dataset select-web` | Every pitcher and batter in `pitches_mlb_{season}.parquet`; scores on each change via `recommend_pitch()`. Open **http://127.0.0.1:8765/** after start. Requires trained `models/situational_model.joblib` (`train-select`). |

Static files for the web app live under `src/pitch_dataset/static/situational_web/`. Canvas: [`situational-selection.canvas.tsx`](/Users/grantdevers/.cursor/projects/Users-grantdevers-Projects-pitch-dataset/canvases/situational-selection.canvas.tsx) (featured matchups; demo HTML is the precomputed grid).

### Traded deadline analysis

Pre/post splits for headline deadline arms (usage mix, full Statcast shape metrics, extended pairing/tunnel vs primary):

```bash
# Default top-5: Skubal, Gausman, Soriano, Mize, Peralta
uv run pitch-dataset traded

# Subset by key or last name
uv run pitch-dataset traded --pitchers skubal,gausman --report reports/traded_pitchers.md --html reports/traded_pitchers.html
```

Outputs: `reports/traded_pitchers.md`, `reports/traded_pitchers.html` (full shape + pairing pre/post deltas), `reports/traded_pitchers_shape.html` (shape/pairing-focused visual with pitcher switcher). Canvases: [`traded-pitchers.canvas.tsx`](/Users/grantdevers/.cursor/projects/Users-grantdevers-Projects-pitch-dataset/canvases/traded-pitchers.canvas.tsx), [`traded-pitchers-shape.canvas.tsx`](/Users/grantdevers/.cursor/projects/Users-grantdevers-Projects-pitch-dataset/canvases/traded-pitchers-shape.canvas.tsx). Copy to Downloads: `cp reports/traded_pitchers_shape.html ~/Downloads/traded-pitchers-shape-visual.html`. Team affiliation is derived from `inning_topbot` + home/away; post-trade samples are partial through the data end date.

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

- **MLB Savant**: pitch-level Statcast via Savant `statcast_search/csv`.
- **MLB Stats API**: public, no key — schedules, 40-man rosters, transactions, boxscore lineups (`statsapi.mlb.com`).
- **FanGraphs**: season leaderboards + platoon splits via FanGraphs JSON API (polite rate limiting built in).
- **Chadwick register**: MLBAM ↔ FanGraphs ↔ BBRef crosswalk via `pybaseball.chadwick_register()`.
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
