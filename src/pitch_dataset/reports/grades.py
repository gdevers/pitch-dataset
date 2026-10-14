"""20–80 scouting grades from league percentiles.

Method (stated in every report footer):

1. Each scale is one metric or a weighted composite of z-scores; z-scores use the mean and
   SD of the *qualified pool* (pitchers ≥ 600 pitches, pitch types ≥ 100 pitches within the
   same pitch family and throwing hand, hitters ≥ 1,000 pitches seen).
2. The composite is converted to a percentile within that pool (mid-rank), and the
   percentile to a grade with ``50 + 10 · Φ⁻¹(p)`` clipped to 20–80. By construction the
   qualified pool averages ~50 with SD ~10; displayed grades round to the nearest 5.
3. Players below the qualifying sample are placed against the same pool and flagged.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from pitch_dataset.reports.context import (
    MIN_BATTER_PITCHES,
    MIN_GROUP_SEEN,
    MIN_PITCH_TYPE_N,
    MIN_PITCHER_PITCHES,
)

Metric = tuple[str, float]  # (column, signed weight)

PITCH_STUFF: list[Metric] = [("stuff100", 1.0)]
PITCH_RESULTS: list[Metric] = [("whiff_pct", 1.0), ("csw_pct", 0.5), ("xwoba", -1.0)]
PITCH_COMMAND: list[Metric] = [("shadow_pct", 1.0), ("waste_pct", -1.0), ("heart_pct", -0.5)]

PITCHER_SCALES: dict[str, list[Metric]] = {
    "stuff": [("stuff100", 1.0)],
    "command": [("BB%", -1.0), ("shadow_pct", 0.75), ("waste_pct", -0.5), ("fstrike_pct", 0.5), ("zone_pct", 0.5)],
    "miss": [("whiff_pct", 1.0), ("K%", 1.0), ("csw_pct", 0.5)],
    "contact": [("xwoba_con", -1.0), ("barrel_pct", -0.75), ("gb_pct", 0.25)],
}
DURABILITY_SP: list[Metric] = [("ip_per_gs", 1.0), ("pitches_per_g", 0.75), ("velo_hold", 0.75)]
DURABILITY_RP: list[Metric] = [("G", 1.0), ("IP", 0.75), ("velo_hold", 0.25)]

BATTER_SCALES: dict[str, list[Metric]] = {
    "hit": [("contact_pct", 1.0), ("xAVG", 1.0), ("K%", -0.75)],
    "power": [("barrel_pct", 1.0), ("ev90", 1.0), ("ISO", 0.75)],
    "discipline": [("chase_pct", -1.0), ("sw_minus_ch", 0.75), ("BB%", 0.75)],
    "pull_air": [("pull_air_pct", 1.0)],
    "speed": [("Spd", 1.0)],
}

SCALE_LABELS = {
    "stuff": "Stuff", "command": "Command", "miss": "Bat-missing", "contact": "Contact mgmt",
    "durability": "Durability", "hit": "Hit", "power": "Power", "discipline": "Discipline",
    "pull_air": "Pull-air", "speed": "Speed", "vs_FB": "vs Fastballs", "vs_BRK": "vs Breaking",
    "vs_OFF": "vs Offspeed",
}


def grade_from_pct(p: np.ndarray | float) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 0.0013, 0.9987)
    return np.clip(50.0 + 10.0 * norm.ppf(p), 20.0, 80.0)


def display_grade(g: float | None) -> int | None:
    if g is None or not np.isfinite(g):
        return None
    return int(5 * round(float(g) / 5))


def grade_word(g: float | None) -> str:
    d = display_grade(g)
    if d is None:
        return "n/a"
    return {80: "elite", 75: "elite", 70: "plus-plus", 65: "plus", 60: "plus", 55: "above-average",
            50: "average", 45: "fringe-average", 40: "below-average", 35: "well below-average",
            30: "poor", 25: "poor", 20: "poor"}[d]


def _pct_in_pool(values: pd.Series, pool: pd.Series) -> pd.Series:
    """Mid-rank percentile of each value against the pool's distribution."""
    ref = np.sort(pool.dropna().to_numpy(float))
    if len(ref) == 0:
        return pd.Series(np.nan, index=values.index)
    v = values.to_numpy(float)
    lo = np.searchsorted(ref, v, side="left")
    hi = np.searchsorted(ref, v, side="right")
    p = (lo + hi) / 2.0 / len(ref)
    p = np.where(np.isfinite(v), p, np.nan)
    return pd.Series(p, index=values.index)


def composite(table: pd.DataFrame, pool: pd.Series, metrics: list[Metric]) -> pd.Series:
    """Weighted mean of pool-standardized z-scores (missing metrics dropped per row)."""
    num = pd.Series(0.0, index=table.index)
    den = pd.Series(0.0, index=table.index)
    for col, w in metrics:
        if col not in table.columns:
            continue
        x = pd.to_numeric(table[col], errors="coerce")
        ref = x[pool]
        sd = ref.std()
        if not np.isfinite(sd) or sd == 0:
            continue
        z = (x - ref.mean()) / sd * np.sign(w)
        ok = z.notna()
        num = num + z.fillna(0.0) * abs(w)
        den = den + ok * abs(w)
    return num / den.where(den > 0)


def grade_scale(table: pd.DataFrame, pool: pd.Series, metrics: list[Metric], *, group: pd.Series | None = None) -> tuple[pd.Series, pd.Series]:
    """(grade, percentile) for every row against the qualified pool (optionally within groups)."""
    grade = pd.Series(np.nan, index=table.index)
    pct = pd.Series(np.nan, index=table.index)
    groups = [(None, pd.Series(True, index=table.index))] if group is None else [
        (k, group == k) for k in group.dropna().unique()
    ]
    for _, rows in groups:
        sub, sub_pool = table[rows], pool[rows]
        if sub_pool.sum() < 5:
            continue
        score = composite(sub, sub_pool, metrics)
        p = _pct_in_pool(score, score[sub_pool])
        pct[rows] = p
        grade[rows] = grade_from_pct(p.to_numpy())
    return grade, pct


def _pct_metric(table: pd.DataFrame, pool: pd.Series, col: str, *, group: pd.Series | None = None, higher_better: bool = True) -> pd.Series:
    """Plain percentile (0–100) for a single display metric, oriented so 100 = best."""
    x = pd.to_numeric(table[col], errors="coerce") * (1 if higher_better else -1)
    out = pd.Series(np.nan, index=table.index)
    keys = [None] if group is None else list(group.dropna().unique())
    for k in keys:
        rows = pd.Series(True, index=table.index) if k is None else group == k
        out[rows] = 100 * _pct_in_pool(x[rows], x[rows & pool])
    return out


def apply_grades(ctx: Any) -> None:
    """Add grade / percentile columns to the context tables and record pool sanity stats."""
    stats: dict[str, Any] = {}

    pt = ctx.pitch_types
    pt_pool = (pt["n"] >= MIN_PITCH_TYPE_N) & pt["fam"].notna()
    pool_key = pt["fam"].fillna("?") + "|" + pt["p_throws"].fillna("R")
    sizes = pool_key[pt_pool].value_counts()
    pool_key = pool_key.where(pool_key.map(sizes).fillna(0) >= 25, pt["fam"].fillna("?"))
    pt["pool_key"] = pool_key
    pt["qualified"] = pt_pool
    for name, metrics in (("stuff", PITCH_STUFF), ("results", PITCH_RESULTS), ("command", PITCH_COMMAND)):
        g, p = grade_scale(pt, pt_pool, metrics, group=pool_key)
        pt[f"g_{name}"], pt[f"p_{name}"] = g, p
        stats[f"pitch_{name}"] = _summ(g[pt_pool])
    for col, hb in (("velo", True), ("whiff_pct", True), ("chase_pct", True), ("xwoba", False),
                    ("ivb", True), ("hb_arm", True), ("spin", True), ("rvn100", True)):
        pt[f"pct_{col}"] = _pct_metric(pt, pt_pool, col, group=pool_key, higher_better=hb)

    pit = ctx.pitchers
    p_pool = pit["n"] >= MIN_PITCHER_PITCHES
    pit["qualified"] = p_pool
    for name, metrics in PITCHER_SCALES.items():
        g, p = grade_scale(pit, p_pool, metrics)
        pit[f"g_{name}"], pit[f"p_{name}"] = g, p
        stats[f"pitcher_{name}"] = _summ(g[p_pool])
    dur = pd.Series(np.nan, index=pit.index)
    for role, metrics in (("SP", DURABILITY_SP), ("RP", DURABILITY_RP)):
        rows = pit["role"] == role
        g, _ = grade_scale(pit[rows], p_pool[rows], metrics)
        dur[rows] = g
    pit["g_durability"] = dur
    stats["pitcher_durability"] = _summ(dur[p_pool])
    for col, hb in (("K%", True), ("BB%", False), ("whiff_pct", True), ("chase_pct", True), ("csw_pct", True),
                    ("xERA", False), ("FIP", False), ("xFIP", False), ("ERA", False), ("xwoba_con", False),
                    ("barrel_pct", False), ("K-BB%", True), ("fb_velo", True), ("stuff100", True)):
        if col in pit.columns:
            pit[f"pct_{col}"] = _pct_metric(pit, p_pool, col, higher_better=hb)

    bat = ctx.batters
    b_pool = (bat["n"] >= MIN_BATTER_PITCHES) & bat["PA"].notna()
    bat["qualified"] = b_pool
    for name, metrics in BATTER_SCALES.items():
        g, p = grade_scale(bat, b_pool, metrics)
        bat[f"g_{name}"], bat[f"p_{name}"] = g, p
        stats[f"batter_{name}"] = _summ(g[b_pool])
    for grp in ("FB", "BRK", "OFF"):
        pool = b_pool & (bat[f"seen_{grp}"] >= MIN_GROUP_SEEN)
        g, _ = grade_scale(bat, pool, [(f"rv100_{grp}", 1.0)])
        bat[f"g_vs_{grp}"] = g
        stats[f"batter_vs_{grp}"] = _summ(g[pool])
    for col, hb in (("wOBA", True), ("xwOBA", True), ("wRC+", True), ("K%", False), ("BB%", True),
                    ("barrel_pct", True), ("hard_pct", True), ("ev_mean", True), ("ev_max", True),
                    ("ev90", True), ("chase_pct", False), ("contact_pct", True), ("xAVG", True),
                    ("ISO", True), ("pull_air_pct", True), ("Spd", True), ("whiff_pct", False),
                    ("AVG", True), ("OBP", True), ("SLG", True), ("sweet_pct", True)):
        if col in bat.columns:
            bat[f"pct_{col}"] = _pct_metric(bat, b_pool, col, higher_better=hb)
    ctx.grades = stats


def _summ(g: pd.Series) -> dict[str, float]:
    g = g.dropna()
    disp = (5 * (g / 5).round())
    return {
        "n": len(g), "mean": round(float(g.mean()), 1) if len(g) else float("nan"),
        "sd": round(float(g.std()), 1) if len(g) > 1 else float("nan"),
        "display_mean": round(float(disp.mean()), 1) if len(g) else float("nan"),
        "display_sd": round(float(disp.std()), 1) if len(g) > 1 else float("nan"),
        "share_60_plus": round(float((disp >= 60).mean()), 3) if len(g) else float("nan"),
    }


def sanity_table(ctx: Any) -> pd.DataFrame:
    rows = [{"scale": k, **v} for k, v in ctx.grades.items()]
    return pd.DataFrame(rows)
