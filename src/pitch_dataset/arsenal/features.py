"""Feature engineering for pitch-value and arsenal optimization."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

# Non-competitive / rare pitch codes excluded from arsenals.
EXCLUDED_PITCH_TYPES = frozenset({"PO", "IN", "UN", "AB", ""})

COUNT_BUCKETS = {
    (0, 0): "0-0",
    (1, 0): "ahead_hit",  # pitcher behind
    (2, 0): "ahead_hit",
    (3, 0): "ahead_hit",
    (3, 1): "ahead_hit",
    (0, 1): "ahead_pit",
    (0, 2): "ahead_pit",
    (1, 2): "ahead_pit",
    (1, 1): "even",
    (2, 1): "even",
    (2, 2): "even",
    (3, 2): "full",
}

CONTEXT_FEATURE_COLS = [
    "platoon_rh",
    "balls",
    "strikes",
    "count_ahead_hit",
    "count_ahead_pit",
    "count_even",
    "count_full",
    "is_2k",
    "zone_heart",
    "zone_shadow",
    "zone_chase",
    "zone_waste",
    "plate_x",
    "plate_z",
    "tto",
    "outs_when_up",
    "runners_on",
    "score_diff",
    "batter_xwoba_prior",
    "prev_same_pitch",
    "prev_is_fastball",
    "pair_velo_sep",
    "pair_mov_sep",
    "pair_release_sim",
]

PITCH_ONEHOT_PREFIX = "pt_"


def prepare_pitches(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and annotate a Statcast pitch frame for modeling."""
    if df.attrs.get("arsenal_prepared") or (
        "target_rv" in df.columns and "pair_velo_sep" in df.columns
    ):
        return df

    out = df.copy()
    if "game_date" in out.columns:
        out["game_date"] = pd.to_datetime(out["game_date"])

    out = out[out["pitch_type"].notna()].copy()
    out["pitch_type"] = out["pitch_type"].astype(str).str.strip().str.upper()
    out = out[~out["pitch_type"].isin(EXCLUDED_PITCH_TYPES)].copy()

    for col in ("balls", "strikes", "outs_when_up", "inning"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)

    out["stand"] = out.get("stand", pd.Series("R", index=out.index)).fillna("R").astype(str)
    out["p_throws"] = (
        out.get("p_throws", pd.Series("R", index=out.index)).fillna("R").astype(str)
    )
    out["platoon_rh"] = (
        ((out["p_throws"] == "R") & (out["stand"] == "R"))
        | ((out["p_throws"] == "L") & (out["stand"] == "L"))
    ).astype(int)
    out["batter_side"] = out["stand"].map({"L": "LHH", "R": "RHH"}).fillna("RHH")

    out["count_bucket"] = [
        COUNT_BUCKETS.get((int(b), int(s)), "even")
        for b, s in zip(out["balls"], out["strikes"], strict=False)
    ]
    out["is_2k"] = (out["strikes"] == 2).astype(int)

    zone = pd.to_numeric(out.get("zone"), errors="coerce")
    out["zone_heart"] = zone.isin([5]).astype(int)
    out["zone_shadow"] = zone.isin([1, 2, 3, 4, 6, 7, 8, 9]).astype(int)
    out["zone_chase"] = zone.isin([11, 12, 13, 14]).astype(int)
    out["zone_waste"] = (~zone.isin([1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14])).astype(int)

    for col in ("plate_x", "plate_z"):
        out[col] = pd.to_numeric(out.get(col), errors="coerce")

    tto = pd.to_numeric(out.get("n_thruorder_pitcher"), errors="coerce")
    out["tto"] = tto.fillna(1).clip(1, 4)

    out["runners_on"] = (
        out.get("on_1b").notna().astype(int)
        + out.get("on_2b").notna().astype(int)
        + out.get("on_3b").notna().astype(int)
    )
    bat_score = pd.to_numeric(out.get("bat_score"), errors="coerce").fillna(0)
    fld_score = pd.to_numeric(out.get("fld_score"), errors="coerce").fillna(0)
    out["score_diff"] = fld_score - bat_score

    out["target_rv"] = pd.to_numeric(out.get("delta_run_exp"), errors="coerce")
    out["target_xwoba"] = _pitch_xwoba(out)

    out = _add_sequence_features(out)
    out = _add_hitter_context(out)
    out = _add_pairing_features(out)
    out = _add_count_dummies(out)
    out = out.reset_index(drop=True)
    out.attrs["arsenal_prepared"] = True
    return out


def arsenal_pitch_types(df: pd.DataFrame, *, min_n: int = 25) -> list[str]:
    counts = df["pitch_type"].value_counts()
    return [str(pt) for pt, n in counts.items() if n >= min_n]


def build_model_matrix(
    df: pd.DataFrame,
    *,
    pitch_types: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return X, y_rv, y_xwoba for training / scoring."""
    frame = df.dropna(subset=["target_rv"]).copy()
    pts = list(pitch_types) if pitch_types is not None else sorted(frame["pitch_type"].unique())
    X = frame[CONTEXT_FEATURE_COLS].copy()
    for col in CONTEXT_FEATURE_COLS:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    X = X.fillna(X.median(numeric_only=True))
    for pt in pts:
        X[f"{PITCH_ONEHOT_PREFIX}{pt}"] = (frame["pitch_type"] == pt).astype(int)
    y_rv = frame["target_rv"].astype(float)
    y_xwoba = frame["target_xwoba"].astype(float)
    return X, y_rv, y_xwoba


def context_row_features(row: pd.Series, pitch_types: Iterable[str]) -> pd.DataFrame:
    """Build one feature row per candidate pitch type for a single context."""
    base = {col: row.get(col, 0) for col in CONTEXT_FEATURE_COLS}
    rows = []
    for pt in pitch_types:
        feat = dict(base)
        for other in pitch_types:
            feat[f"{PITCH_ONEHOT_PREFIX}{other}"] = int(other == pt)
        # Pairing vs previous pitch should reflect candidate pitch vs prev.
        prev = row.get("prev_pitch_type")
        if isinstance(prev, str) and prev and prev != "NONE":
            feat["prev_same_pitch"] = int(prev == pt)
            feat["prev_is_fastball"] = int(prev in {"FF", "SI", "FC", "FA"})
        rows.append(feat)
    return pd.DataFrame(rows)


def _pitch_xwoba(df: pd.DataFrame) -> pd.Series:
    """Approximate pitch-level expected wOBA for reporting."""
    est = pd.to_numeric(df.get("estimated_woba_using_speedangle"), errors="coerce")
    woba = pd.to_numeric(df.get("woba_value"), errors="coerce")
    denom = pd.to_numeric(df.get("woba_denom"), errors="coerce")
    desc = df.get("description", pd.Series(index=df.index, dtype=object)).fillna("")
    events = df.get("events", pd.Series(index=df.index, dtype=object)).fillna("")

    # Terminal PA outcomes first.
    out = pd.Series(np.nan, index=df.index, dtype=float)
    terminal = denom.fillna(0).eq(1) & woba.notna()
    out = out.where(~terminal, woba)

    bip = est.notna() & out.isna()
    out = out.where(~bip, est)

    # Non-terminal contact / take mapping (league-ish priors).
    desc_map = {
        "swinging_strike": 0.05,
        "swinging_strike_blocked": 0.05,
        "called_strike": 0.08,
        "foul": 0.18,
        "foul_tip": 0.10,
        "ball": 0.42,
        "blocked_ball": 0.42,
        "hit_into_play": 0.32,
        "hit_into_play_score": 0.55,
        "hit_into_play_no_out": 0.55,
    }
    for key, val in desc_map.items():
        mask = out.isna() & desc.eq(key)
        out = out.where(~mask, val)

    # Event fallbacks.
    event_map = {
        "strikeout": 0.0,
        "strikeout_double_play": 0.0,
        "walk": 0.69,
        "intent_walk": 0.69,
        "hit_by_pitch": 0.72,
        "single": 0.88,
        "double": 1.24,
        "triple": 1.56,
        "home_run": 2.00,
        "field_out": 0.0,
        "force_out": 0.0,
        "grounded_into_double_play": 0.0,
        "sac_fly": 0.0,
        "sac_bunt": 0.0,
    }
    for key, val in event_map.items():
        mask = out.isna() & events.eq(key)
        out = out.where(~mask, val)

    return out.fillna(0.32)


def _add_sequence_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(
        [c for c in ("game_pk", "at_bat_number", "pitch_number") if c in df.columns]
    ).copy()
    group_cols = [c for c in ("game_pk", "at_bat_number") if c in out.columns]
    if not group_cols:
        out["prev_pitch_type"] = "NONE"
        out["prev_same_pitch"] = 0
        out["prev_is_fastball"] = 0
        return out

    prev = out.groupby(group_cols, sort=False)["pitch_type"].shift(1)
    out["prev_pitch_type"] = prev.fillna("NONE")
    out["prev_same_pitch"] = (out["prev_pitch_type"] == out["pitch_type"]).astype(int)
    out["prev_is_fastball"] = out["prev_pitch_type"].isin({"FF", "SI", "FC", "FA"}).astype(int)
    return out


def _add_hitter_context(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "batter" not in out.columns:
        out["batter_xwoba_prior"] = 0.320
        return out
    # Season-to-date batter mean excluding current pitch (shifted expanding mean).
    sort_cols = [
        c
        for c in ("game_date", "game_pk", "at_bat_number", "pitch_number")
        if c in out.columns
    ]
    ordered = out.sort_values(sort_cols) if sort_cols else out
    shifted = ordered.groupby("batter", sort=False)["target_xwoba"].shift(1)
    prior = shifted.groupby(ordered["batter"], sort=False).expanding(min_periods=10).mean()
    prior.index = ordered.index
    out["batter_xwoba_prior"] = prior.reindex(out.index).fillna(0.320)
    return out


def _add_pairing_features(df: pd.DataFrame) -> pd.DataFrame:
    """Pitcher-level arsenal pairing: velo/movement separation + release similarity."""
    out = df.copy()
    metrics = ["release_speed", "pfx_x", "pfx_z", "release_pos_x", "release_pos_z"]
    drop_cols = [
        c
        for c in out.columns
        if c.startswith(("avg_", "pri_"))
        or c in {"pair_velo_sep", "pair_mov_sep", "pair_release_sim", "primary_pitch"}
    ]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    for col in metrics:
        out[col] = pd.to_numeric(out.get(col), errors="coerce")

    arsenal = (
        out.groupby(["pitcher", "pitch_type"], as_index=False)[metrics]
        .mean()
        .rename(columns={c: f"avg_{c}" for c in metrics})
    )
    # Primary pitch = most thrown.
    primary = (
        out.groupby(["pitcher", "pitch_type"])
        .size()
        .reset_index(name="n")
        .sort_values(["pitcher", "n"], ascending=[True, False])
        .groupby("pitcher", as_index=False)
        .first()[["pitcher", "pitch_type"]]
        .rename(columns={"pitch_type": "primary_pitch"})
    )
    primary_metrics = arsenal.merge(
        primary, left_on=["pitcher", "pitch_type"], right_on=["pitcher", "primary_pitch"]
    )
    primary_metrics = primary_metrics.rename(
        columns={f"avg_{c}": f"pri_{c}" for c in metrics}
    )[["pitcher", "primary_pitch"] + [f"pri_{c}" for c in metrics]]

    merged = out.merge(arsenal, on=["pitcher", "pitch_type"], how="left")
    merged = merged.merge(primary_metrics, on="pitcher", how="left")

    merged["pair_velo_sep"] = (
        merged["avg_release_speed"] - merged["pri_release_speed"]
    ).abs()
    merged["pair_mov_sep"] = np.sqrt(
        (merged["avg_pfx_x"] - merged["pri_pfx_x"]).fillna(0) ** 2
        + (merged["avg_pfx_z"] - merged["pri_pfx_z"]).fillna(0) ** 2
    )
    release_dist = np.sqrt(
        (merged["avg_release_pos_x"] - merged["pri_release_pos_x"]).fillna(0) ** 2
        + (merged["avg_release_pos_z"] - merged["pri_release_pos_z"]).fillna(0) ** 2
    )
    # Higher = more similar release (tunnel proxy). Cap distance effect.
    merged["pair_release_sim"] = 1.0 / (1.0 + release_dist)

    # Same as primary → separations near 0, similarity 1.
    is_primary = merged["pitch_type"] == merged["primary_pitch"]
    merged.loc[is_primary, "pair_velo_sep"] = 0.0
    merged.loc[is_primary, "pair_mov_sep"] = 0.0
    merged.loc[is_primary, "pair_release_sim"] = 1.0

    for col in ("pair_velo_sep", "pair_mov_sep", "pair_release_sim"):
        merged[col] = merged[col].fillna(merged[col].median())
    return merged


def _add_count_dummies(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for name in ("ahead_hit", "ahead_pit", "even", "full"):
        out[f"count_{name}"] = (out["count_bucket"] == name).astype(int)
    # 0-0 maps into even via COUNT_BUCKETS missing; treat explicitly.
    out.loc[out["count_bucket"] == "0-0", "count_even"] = 1
    return out
