"""Pitch arsenal optimization: features → outcome model → usage optimize → report.

Single module for the hiring walkthrough: prepare Statcast pitches, train a
dual-target outcome model (run value + pitch xwOBA), solve constrained usage
mixes per pitcher segment, and format markdown recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------

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

# Statcast shape fields used for pitch-level features and pairing/tunnel logic.
SHAPE_METRIC_COLS = [
    "release_speed",
    "effective_speed",
    "release_extension",
    "release_spin_rate",
    "spin_axis",
    "arm_angle",
    "release_pos_x",
    "release_pos_y",
    "release_pos_z",
    "pfx_x",
    "pfx_z",
    "api_break_x_arm",
    "api_break_x_batter_in",
    "api_break_z_with_gravity",
]

# Pitch-level shape features fed to the outcome model (raw Statcast per pitch).
PITCH_SHAPE_FEATURE_COLS = [
    "arm_angle",
    "release_spin_rate",
    "spin_axis",
    "release_extension",
    "effective_speed",
    "release_pos_y",
    "api_break_x_arm",
    "api_break_x_batter_in",
    "api_break_z_with_gravity",
]

# Pairing outputs vs primary pitch (pitcher-level arsenal means).
PAIRING_FEATURE_COLS = [
    "pair_velo_sep",
    "pair_mov_sep",
    "pair_release_sim",
    "pair_eff_speed_sep",
    "pair_arm_sep",
    "pair_extension_sep",
    "pair_spin_sep",
    "pair_spin_axis_sep",
    "pair_break_sep",
]

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
    *PITCH_SHAPE_FEATURE_COLS,
    *PAIRING_FEATURE_COLS,
]

PITCH_ONEHOT_PREFIX = "pt_"

DEFAULT_MODEL_PATH = Path("models/outcome_model.joblib")


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
    out = _coerce_shape_metrics(out)
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


def context_row_features(
    row: pd.Series,
    pitch_types: Iterable[str],
    *,
    arsenal_means: pd.DataFrame | None = None,
    primary_pitch: str | None = None,
) -> pd.DataFrame:
    """Build one feature row per candidate pitch type for a single context."""
    base = {col: row.get(col, 0) for col in CONTEXT_FEATURE_COLS}
    if arsenal_means is not None and primary_pitch:
        primary_row = arsenal_means.loc[primary_pitch] if primary_pitch in arsenal_means.index else None
    else:
        primary_row = None

    rows = []
    for pt in pitch_types:
        feat = dict(base)
        for other in pitch_types:
            feat[f"{PITCH_ONEHOT_PREFIX}{other}"] = int(other == pt)
        prev = row.get("prev_pitch_type")
        if isinstance(prev, str) and prev and prev != "NONE":
            feat["prev_same_pitch"] = int(prev == pt)
            feat["prev_is_fastball"] = int(prev in {"FF", "SI", "FC", "FA"})
        if arsenal_means is not None and primary_pitch and pt in arsenal_means.index:
            feat.update(pairing_features_for_type(arsenal_means, primary_pitch, pt))
            for col in PITCH_SHAPE_FEATURE_COLS:
                if col in arsenal_means.columns:
                    feat[col] = float(arsenal_means.loc[pt, col])
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


def _coerce_shape_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in PITCH_SHAPE_FEATURE_COLS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _circular_sep(a: float, b: float, *, period: float = 360.0) -> float:
    diff = abs(float(a) - float(b)) % period
    return min(diff, period - diff)


def _euclidean_sep(
    row_a: pd.Series,
    row_b: pd.Series,
    cols: list[str],
) -> float:
    total = 0.0
    for col in cols:
        if col not in row_a.index or col not in row_b.index:
            continue
        av = row_a[col]
        bv = row_b[col]
        if pd.isna(av) or pd.isna(bv):
            continue
        total += (float(av) - float(bv)) ** 2
    return float(np.sqrt(total))


def pitcher_arsenal_means(
    df: pd.DataFrame,
    *,
    metrics: list[str] | None = None,
) -> pd.DataFrame:
    """Pitch-type means for one pitcher's subset."""
    metrics = metrics or SHAPE_METRIC_COLS
    cols = [c for c in metrics if c in df.columns]
    if not cols or df.empty:
        return pd.DataFrame()
    return df.groupby("pitch_type", as_index=True)[cols].mean(numeric_only=True)


def primary_pitch_type(df: pd.DataFrame) -> str | None:
    if df.empty:
        return None
    return str(df["pitch_type"].value_counts().idxmax())


def pairing_features_for_type(
    arsenal_means: pd.DataFrame,
    primary: str,
    candidate: str,
) -> dict[str, float]:
    """Pairing/tunnel features for a candidate pitch vs the primary pitch."""
    out = {col: 0.0 for col in PAIRING_FEATURE_COLS}
    if primary not in arsenal_means.index or candidate not in arsenal_means.index:
        return out

    pri = arsenal_means.loc[primary]
    cand = arsenal_means.loc[candidate]
    is_primary = candidate == primary

    if "release_speed" in arsenal_means.columns:
        out["pair_velo_sep"] = 0.0 if is_primary else abs(
            float(cand["release_speed"]) - float(pri["release_speed"])
        )
    if {"pfx_x", "pfx_z"}.issubset(arsenal_means.columns):
        out["pair_mov_sep"] = 0.0 if is_primary else _euclidean_sep(cand, pri, ["pfx_x", "pfx_z"])
    rel_cols = [c for c in ("release_pos_x", "release_pos_y", "release_pos_z") if c in arsenal_means.columns]
    if rel_cols:
        rel = 0.0 if is_primary else _euclidean_sep(cand, pri, rel_cols)
        out["pair_release_sim"] = 1.0 if is_primary else 1.0 / (1.0 + rel)
    if "effective_speed" in arsenal_means.columns:
        out["pair_eff_speed_sep"] = 0.0 if is_primary else abs(
            float(cand["effective_speed"]) - float(pri["effective_speed"])
        )
    if "arm_angle" in arsenal_means.columns:
        out["pair_arm_sep"] = 0.0 if is_primary else abs(
            float(cand["arm_angle"]) - float(pri["arm_angle"])
        )
    if "release_extension" in arsenal_means.columns:
        out["pair_extension_sep"] = 0.0 if is_primary else abs(
            float(cand["release_extension"]) - float(pri["release_extension"])
        )
    if "release_spin_rate" in arsenal_means.columns:
        out["pair_spin_sep"] = 0.0 if is_primary else abs(
            float(cand["release_spin_rate"]) - float(pri["release_spin_rate"])
        )
    if "spin_axis" in arsenal_means.columns:
        out["pair_spin_axis_sep"] = 0.0 if is_primary else _circular_sep(
            float(cand["spin_axis"]), float(pri["spin_axis"])
        )
    break_cols = [c for c in (
        "api_break_x_arm", "api_break_x_batter_in", "api_break_z_with_gravity"
    ) if c in arsenal_means.columns]
    if break_cols:
        out["pair_break_sep"] = 0.0 if is_primary else _euclidean_sep(cand, pri, break_cols)
    return out


def pairing_note_for_type(
    arsenal_means: pd.DataFrame,
    primary: str,
    candidate: str,
) -> str:
    """Human-readable pairing note for reports."""
    if primary not in arsenal_means.index or candidate not in arsenal_means.index:
        return ""
    if candidate == primary:
        return ""

    pri = arsenal_means.loc[primary]
    row = arsenal_means.loc[candidate]
    feats = pairing_features_for_type(arsenal_means, primary, candidate)

    rel_cols = [c for c in ("release_pos_x", "release_pos_y", "release_pos_z") if c in arsenal_means.columns]
    rel = _euclidean_sep(row, pri, rel_cols) if rel_cols else 0.0
    tunnel = (
        "strong tunnel" if rel < 0.25 else ("moderate tunnel" if rel < 0.45 else "distinct release")
    )

    header = f"{candidate} vs primary {primary}"
    details = [
        f"velo sep {feats['pair_velo_sep']:.1f} mph",
        f"move sep {feats['pair_mov_sep']:.1f} in",
    ]
    if pd.notna(feats["pair_eff_speed_sep"]) and feats["pair_eff_speed_sep"]:
        details.append(f"eff speed sep {feats['pair_eff_speed_sep']:.1f} mph")
    if pd.notna(feats["pair_spin_sep"]) and feats["pair_spin_sep"]:
        details.append(f"spin sep {feats['pair_spin_sep']:.0f} rpm")
    if pd.notna(feats["pair_spin_axis_sep"]) and feats["pair_spin_axis_sep"]:
        details.append(f"spin axis sep {feats['pair_spin_axis_sep']:.0f}°")
    if pd.notna(feats["pair_arm_sep"]) and feats["pair_arm_sep"]:
        details.append(f"arm angle sep {feats['pair_arm_sep']:.1f}°")
    if pd.notna(feats["pair_extension_sep"]) and feats["pair_extension_sep"]:
        details.append(f"extension sep {feats['pair_extension_sep']:.2f} ft")
    if pd.notna(feats["pair_break_sep"]) and feats["pair_break_sep"]:
        details.append(f"API break sep {feats['pair_break_sep']:.1f} in")
    details.append(f"release {tunnel} ({rel:.2f} ft)")
    return f"{header}: {', '.join(details)}"


def _add_pairing_features(df: pd.DataFrame) -> pd.DataFrame:
    """Pitcher-level arsenal pairing: shape separation + release similarity."""
    out = df.copy()
    metrics = [c for c in SHAPE_METRIC_COLS if c in out.columns]
    drop_cols = [
        c
        for c in out.columns
        if c.startswith(("avg_", "pri_"))
        or c in PAIRING_FEATURE_COLS
        or c == "primary_pitch"
    ]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    for col in metrics:
        out[col] = pd.to_numeric(out.get(col), errors="coerce")

    if not metrics or "pitcher" not in out.columns:
        for col in PAIRING_FEATURE_COLS:
            out[col] = 0.0
        return out

    arsenal = (
        out.groupby(["pitcher", "pitch_type"], as_index=False)[metrics]
        .mean()
        .rename(columns={c: f"avg_{c}" for c in metrics})
    )
    primary = (
        out.groupby(["pitcher", "pitch_type"])
        .size()
        .reset_index(name="n")
        .sort_values(["pitcher", "n"], ascending=[True, False])
        .groupby("pitcher", as_index=False)
        .first()[["pitcher", "pitch_type"]]
        .rename(columns={"pitch_type": "primary_pitch"})
    )

    merged = out.merge(arsenal, on=["pitcher", "pitch_type"], how="left")
    merged = merged.merge(primary, on="pitcher", how="left")

    for col in PAIRING_FEATURE_COLS:
        merged[col] = np.nan

    for pitcher_id, idx in merged.groupby("pitcher").groups.items():
        sub = merged.loc[idx]
        means = pitcher_arsenal_means(sub, metrics=metrics)
        primary_pt = primary_pitch_type(sub)
        if primary_pt is None or means.empty:
            continue
        for row_idx, pt in zip(sub.index, sub["pitch_type"], strict=False):
            feats = pairing_features_for_type(means, primary_pt, str(pt))
            for col, val in feats.items():
                merged.at[row_idx, col] = val

    for col in PAIRING_FEATURE_COLS:
        merged[col] = merged[col].fillna(merged[col].median())
    return merged


def _add_count_dummies(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for name in ("ahead_hit", "ahead_pit", "even", "full"):
        out[f"count_{name}"] = (out["count_bucket"] == name).astype(int)
    # 0-0 maps into even via COUNT_BUCKETS missing; treat explicitly.
    out.loc[out["count_bucket"] == "0-0", "count_even"] = 1
    return out


# ---------------------------------------------------------------------------
# Outcome model
# ---------------------------------------------------------------------------


@dataclass
class OutcomeModel:
    """Trained dual-target pitch outcome model (RV + xwOBA)."""

    rv_model: HistGradientBoostingRegressor
    xwoba_model: HistGradientBoostingRegressor
    feature_names: list[str]
    pitch_types: list[str]
    meta: dict[str, Any] = field(default_factory=dict)

    def predict_rv(self, X: pd.DataFrame) -> np.ndarray:
        return self.rv_model.predict(_align_features(X, self.feature_names))

    def predict_xwoba(self, X: pd.DataFrame) -> np.ndarray:
        return self.xwoba_model.predict(_align_features(X, self.feature_names))

    def save(self, path: Path | str = DEFAULT_MODEL_PATH) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path


def load_outcome_model(path: Path | str = DEFAULT_MODEL_PATH) -> OutcomeModel:
    obj = joblib.load(path)
    if not isinstance(obj, OutcomeModel):
        raise TypeError(f"Expected OutcomeModel at {path}, got {type(obj)}")
    return obj


def train_outcome_model(
    pitches: pd.DataFrame,
    *,
    model_path: Path | str = DEFAULT_MODEL_PATH,
    test_size: float = 0.2,
    random_state: int = 42,
    min_pitch_n: int = 200,
) -> tuple[OutcomeModel, dict[str, Any]]:
    """Train outcome models and persist to disk."""
    prepared = prepare_pitches(pitches)
    pitch_types = arsenal_pitch_types(prepared, min_n=min_pitch_n)
    if len(pitch_types) < 2:
        pitch_types = arsenal_pitch_types(prepared, min_n=50)

    X, y_rv, y_xwoba = build_model_matrix(prepared, pitch_types=pitch_types)
    X_train, X_test, y_rv_train, y_rv_test, y_x_train, y_x_test = train_test_split(
        X,
        y_rv,
        y_xwoba,
        test_size=test_size,
        random_state=random_state,
    )

    rv_model = HistGradientBoostingRegressor(
        max_depth=6,
        learning_rate=0.08,
        max_iter=250,
        l2_regularization=0.1,
        random_state=random_state,
    )
    xwoba_model = HistGradientBoostingRegressor(
        max_depth=6,
        learning_rate=0.08,
        max_iter=250,
        l2_regularization=0.1,
        random_state=random_state,
    )
    rv_model.fit(X_train, y_rv_train)
    xwoba_model.fit(X_train, y_x_train)

    rv_pred = rv_model.predict(X_test)
    x_pred = xwoba_model.predict(X_test)
    metrics = {
        "n_pitches": int(len(prepared)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "date_min": str(prepared["game_date"].min().date())
        if "game_date" in prepared.columns
        else None,
        "date_max": str(prepared["game_date"].max().date())
        if "game_date" in prepared.columns
        else None,
        "rv_mae": float(mean_absolute_error(y_rv_test, rv_pred)),
        "rv_r2": float(r2_score(y_rv_test, rv_pred)),
        "xwoba_mae": float(mean_absolute_error(y_x_test, x_pred)),
        "xwoba_r2": float(r2_score(y_x_test, x_pred)),
        "pitch_types": pitch_types,
    }

    model = OutcomeModel(
        rv_model=rv_model,
        xwoba_model=xwoba_model,
        feature_names=list(X.columns),
        pitch_types=pitch_types,
        meta=metrics,
    )
    model.save(model_path)
    return model, metrics


def score_pitch_choices(
    model: OutcomeModel,
    context_features: pd.DataFrame,
    pitch_types: list[str],
) -> pd.DataFrame:
    """Score each candidate pitch type for rows of shared context features.

    ``context_features`` should already include pitch one-hots for each candidate
    (one row per candidate pitch).
    """
    rv = model.predict_rv(context_features)
    xw = model.predict_xwoba(context_features)
    return pd.DataFrame(
        {
            "pitch_type": pitch_types,
            "pred_rv": rv,
            "pred_xwoba": xw,
        }
    )


def _align_features(X: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    aligned = X.copy()
    for name in feature_names:
        if name not in aligned.columns:
            aligned[name] = 0.0
    return aligned[feature_names].fillna(0.0)


# ---------------------------------------------------------------------------
# Optimize
# ---------------------------------------------------------------------------


@dataclass
class UsageChange:
    pitch_type: str
    current_pct: float
    recommended_pct: float
    delta_pct: float


@dataclass
class SegmentRecommendation:
    segment: str
    n_pitches: int
    current_xwoba: float
    optimized_xwoba: float
    expected_improvement_xwoba: float
    current_rv: float
    optimized_rv: float
    expected_improvement_rv: float
    changes: list[UsageChange] = field(default_factory=list)


@dataclass
class PitcherRecommendation:
    pitcher_id: int
    pitcher_name: str
    n_pitches: int
    arsenal: list[str]
    overall_current_xwoba: float
    overall_optimized_xwoba: float
    expected_improvement_xwoba: float
    overall_current_rv: float
    overall_optimized_rv: float
    expected_improvement_rv: float
    segments: list[SegmentRecommendation] = field(default_factory=list)
    pairing_notes: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def optimize_pitcher(
    pitches: pd.DataFrame,
    model: OutcomeModel,
    *,
    pitcher: int | str | None = None,
    pitcher_name: str | None = None,
    min_arsenal_n: int = 30,
    min_segment_n: int = 40,
    min_pct: float = 0.03,
    max_pct: float = 0.55,
    max_shift: float = 0.15,
) -> PitcherRecommendation:
    """Optimize one pitcher's usage vs modeled pitch values."""
    prepared = prepare_pitches(pitches)
    subset = _select_pitcher(prepared, pitcher=pitcher, pitcher_name=pitcher_name)
    if subset.empty:
        raise ValueError(f"No pitches found for pitcher={pitcher!r} name={pitcher_name!r}")

    pitcher_id = int(subset["pitcher"].iloc[0])
    name = str(subset["player_name"].iloc[0])
    arsenal = arsenal_pitch_types(subset, min_n=min_arsenal_n)
    if len(arsenal) < 2:
        arsenal = arsenal_pitch_types(subset, min_n=10)
    if len(arsenal) < 2:
        raise ValueError(f"{name} has fewer than 2 pitch types with enough samples")

    subset = subset[subset["pitch_type"].isin(arsenal)].copy()
    pairing_notes = _pairing_notes(subset, arsenal)

    segments: list[SegmentRecommendation] = []
    # Primary split: platoon (batter side). Secondary: count state.
    for side, side_df in subset.groupby("batter_side"):
        if len(side_df) < min_segment_n:
            continue
        seg = _optimize_segment(
            side_df,
            model=model,
            arsenal=arsenal,
            segment=f"vs {side}",
            min_pct=min_pct,
            max_pct=max_pct,
            max_shift=max_shift,
        )
        segments.append(seg)

        for count_name, count_df in side_df.groupby("count_bucket"):
            if len(count_df) < min_segment_n:
                continue
            if count_name == "0-0":
                label = f"vs {side} | 0-0"
            else:
                label = f"vs {side} | {count_name}"
            segments.append(
                _optimize_segment(
                    count_df,
                    model=model,
                    arsenal=arsenal,
                    segment=label,
                    min_pct=min_pct,
                    max_pct=max_pct,
                    max_shift=max_shift,
                )
            )

    # Overall = pitch-weighted average of platoon segments only.
    platoon_segs = [s for s in segments if s.segment.startswith("vs ") and "|" not in s.segment]
    if not platoon_segs:
        platoon_segs = [
            _optimize_segment(
                subset,
                model=model,
                arsenal=arsenal,
                segment="overall",
                min_pct=min_pct,
                max_pct=max_pct,
                max_shift=max_shift,
            )
        ]
        segments = platoon_segs + segments

    total_n = sum(s.n_pitches for s in platoon_segs)
    w = np.array([s.n_pitches / total_n for s in platoon_segs], dtype=float)
    cur_x = float(np.dot(w, [s.current_xwoba for s in platoon_segs]))
    opt_x = float(np.dot(w, [s.optimized_xwoba for s in platoon_segs]))
    cur_rv = float(np.dot(w, [s.current_rv for s in platoon_segs]))
    opt_rv = float(np.dot(w, [s.optimized_rv for s in platoon_segs]))

    return PitcherRecommendation(
        pitcher_id=pitcher_id,
        pitcher_name=name,
        n_pitches=int(len(subset)),
        arsenal=arsenal,
        overall_current_xwoba=cur_x,
        overall_optimized_xwoba=opt_x,
        expected_improvement_xwoba=opt_x - cur_x,
        overall_current_rv=cur_rv,
        overall_optimized_rv=opt_rv,
        expected_improvement_rv=opt_rv - cur_rv,
        segments=segments,
        pairing_notes=pairing_notes,
        meta={"min_pct": min_pct, "max_pct": max_pct, "max_shift": max_shift},
    )


def optimize_pitchers(
    pitches: pd.DataFrame,
    model: OutcomeModel,
    *,
    pitcher_ids: list[int] | None = None,
    top_n: int = 3,
    **kwargs: Any,
) -> list[PitcherRecommendation]:
    prepared = prepare_pitches(pitches)
    if pitcher_ids is None:
        counts = prepared.groupby("pitcher").size().sort_values(ascending=False)
        pitcher_ids = [int(i) for i in counts.head(top_n).index.tolist()]
    return [
        optimize_pitcher(prepared, model, pitcher=pid, **kwargs) for pid in pitcher_ids
    ]


def _select_pitcher(
    df: pd.DataFrame,
    *,
    pitcher: int | str | None,
    pitcher_name: str | None,
) -> pd.DataFrame:
    if pitcher is not None:
        try:
            pid = int(pitcher)
            return df[df["pitcher"] == pid].copy()
        except (TypeError, ValueError):
            # Treat as name substring.
            pitcher_name = str(pitcher)

    if pitcher_name:
        needle = pitcher_name.strip().lower()
        names = df["player_name"].fillna("").astype(str)
        # Support "Last, First" and "First Last".
        mask = names.str.lower().str.contains(needle, regex=False)
        if not mask.any() and " " in needle:
            parts = [p for p in needle.replace(",", " ").split() if p]
            if len(parts) >= 2:
                # Try "last, first"
                alt = f"{parts[-1]}, {parts[0]}"
                mask = names.str.lower().str.contains(alt, regex=False)
                if not mask.any():
                    mask = names.str.lower().apply(
                        lambda s: all(p in s.lower() for p in parts)
                    )
        return df[mask].copy()
    raise ValueError("Provide --pitcher MLBAM id or name")


def _optimize_segment(
    seg: pd.DataFrame,
    *,
    model: OutcomeModel,
    arsenal: list[str],
    segment: str,
    min_pct: float,
    max_pct: float,
    max_shift: float,
) -> SegmentRecommendation:
    current = (
        seg["pitch_type"].value_counts(normalize=True).reindex(arsenal, fill_value=0.0)
    )
    current_pct = current.to_numpy(dtype=float)
    # Renormalize in case some arsenal pitches absent in segment.
    if current_pct.sum() <= 0:
        current_pct = np.ones(len(arsenal)) / len(arsenal)
    else:
        current_pct = current_pct / current_pct.sum()

    values = _expected_values(seg, model=model, arsenal=arsenal)
    rv = values["pred_rv"].to_numpy(dtype=float)
    xw = values["pred_xwoba"].to_numpy(dtype=float)

    opt_pct = _solve_usage(
        current_pct,
        values=xw,  # minimize expected xwOBA allowed against pitcher
        min_pct=min_pct,
        max_pct=max_pct,
        max_shift=max_shift,
    )

    cur_x = float(np.dot(current_pct, xw))
    opt_x = float(np.dot(opt_pct, xw))
    cur_rv = float(np.dot(current_pct, rv))
    opt_rv = float(np.dot(opt_pct, rv))

    changes = [
        UsageChange(
            pitch_type=pt,
            current_pct=float(current_pct[i]),
            recommended_pct=float(opt_pct[i]),
            delta_pct=float(opt_pct[i] - current_pct[i]),
        )
        for i, pt in enumerate(arsenal)
    ]
    changes.sort(key=lambda c: abs(c.delta_pct), reverse=True)

    return SegmentRecommendation(
        segment=segment,
        n_pitches=int(len(seg)),
        current_xwoba=cur_x,
        optimized_xwoba=opt_x,
        expected_improvement_xwoba=opt_x - cur_x,
        current_rv=cur_rv,
        optimized_rv=opt_rv,
        expected_improvement_rv=opt_rv - cur_rv,
        changes=changes,
    )


def _expected_values(
    seg: pd.DataFrame,
    *,
    model: OutcomeModel,
    arsenal: list[str],
) -> pd.DataFrame:
    """Average predicted RV/xwOBA for each arsenal pitch under segment contexts."""
    ctx = seg
    if len(ctx) > 400:
        ctx = ctx.sample(n=400, random_state=42)

    base = ctx[CONTEXT_FEATURE_COLS].copy()
    for col in CONTEXT_FEATURE_COLS:
        base[col] = pd.to_numeric(base[col], errors="coerce")
    base = base.fillna(base.median(numeric_only=True)).fillna(0.0)

    arsenal_means = pitcher_arsenal_means(seg)
    primary = primary_pitch_type(seg)

    rows = []
    for pt in arsenal:
        feat = base.copy()
        for other in model.pitch_types:
            feat[f"{PITCH_ONEHOT_PREFIX}{other}"] = 0
        col = f"{PITCH_ONEHOT_PREFIX}{pt}"
        if col not in feat.columns:
            feat[col] = 0
        feat[col] = 1
        if "prev_pitch_type" in ctx.columns:
            feat["prev_same_pitch"] = (ctx["prev_pitch_type"].to_numpy() == pt).astype(int)
        if not arsenal_means.empty and primary:
            for shape_col in PITCH_SHAPE_FEATURE_COLS:
                if shape_col in arsenal_means.columns and pt in arsenal_means.index:
                    feat[shape_col] = float(arsenal_means.loc[pt, shape_col])
            for pair_col, val in pairing_features_for_type(
                arsenal_means, primary, pt
            ).items():
                feat[pair_col] = val
        pred_rv = model.predict_rv(feat)
        pred_x = model.predict_xwoba(feat)
        rows.append(
            {
                "pitch_type": pt,
                "pred_rv": float(np.mean(pred_rv)),
                "pred_xwoba": float(np.mean(pred_x)),
            }
        )
    return pd.DataFrame(rows)


def _solve_usage(
    current: np.ndarray,
    *,
    values: np.ndarray,
    min_pct: float,
    max_pct: float,
    max_shift: float,
) -> np.ndarray:
    n = len(current)
    # Established pitches (>=5%) can move within shift caps; fringe pitches stay fixed.
    lowers = []
    uppers = []
    for p in current:
        if p < 0.05:
            lowers.append(float(p))
            uppers.append(float(p))
        else:
            lo = max(min_pct, p - max_shift)
            hi = min(max_pct, p + max_shift)
            if lo > hi:
                lo, hi = hi, lo
            lowers.append(lo)
            uppers.append(hi)
    lowers_a = np.array(lowers, dtype=float)
    uppers_a = np.array(uppers, dtype=float)

    # If bounds cannot sum to 1, relax established pitches to [min_pct, max_pct].
    if lowers_a.sum() > 1.0 + 1e-6 or uppers_a.sum() < 1.0 - 1e-6:
        lowers_a = np.where(current >= 0.05, min_pct, current)
        uppers_a = np.where(current >= 0.05, max_pct, current)

    def objective(w: np.ndarray) -> float:
        return float(np.dot(w, values))

    cons = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    bounds = list(zip(lowers_a, uppers_a, strict=True))
    x0 = np.clip(current, lowers_a, uppers_a)
    if x0.sum() == 0:
        x0 = np.ones(n) / n
    else:
        x0 = x0 / x0.sum()

    result = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=cons,
        options={"maxiter": 200, "ftol": 1e-9},
    )
    if not result.success:
        # Greedy fallback: shift mass toward lowest-value pitches.
        w = current.copy()
        order = np.argsort(values)
        budget = max_shift
        for i in order:
            if w[i] < 0.05:
                continue
            target = min(uppers_a[i], w[i] + budget)
            gain = target - w[i]
            if gain <= 0:
                continue
            donors = np.argsort(-values)
            need = gain
            for j in donors:
                if j == i or w[j] < 0.05:
                    continue
                give = min(need, w[j] - lowers_a[j])
                if give <= 0:
                    continue
                w[j] -= give
                w[i] += give
                need -= give
                if need <= 1e-9:
                    break
            budget -= gain - need
            if budget <= 1e-9:
                break
        w = np.clip(w, 0, None)
        w = w / w.sum()
        return w

    w = np.clip(result.x, 0, None)
    return w / w.sum()


def _pairing_notes(df: pd.DataFrame, arsenal: list[str]) -> list[str]:
    means = pitcher_arsenal_means(df)
    primary = primary_pitch_type(df)
    if means.empty or primary is None or primary not in means.index:
        return []
    notes: list[str] = []
    for pt in arsenal:
        if pt == primary or pt not in means.index:
            continue
        note = pairing_note_for_type(means, primary, pt)
        if note:
            notes.append(note)
    return notes


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def format_recommendation_report(
    recs: list[PitcherRecommendation] | PitcherRecommendation,
    *,
    title: str = "Pitch Arsenal Optimization Report",
    data_note: str | None = None,
) -> str:
    if isinstance(recs, PitcherRecommendation):
        recs = [recs]

    lines: list[str] = [f"# {title}", ""]
    if data_note:
        lines.extend([data_note, ""])

    lines.append(
        "Recommendations compare **actual usage** to a constrained optimal mix "
        "that minimizes predicted pitch-level xwOBA (lower is better for the pitcher), "
        "holding location/count/TTO/context fixed and only reallocating pitch-type share."
    )
    lines.append("")

    for rec in recs:
        lines.extend(_format_pitcher(rec))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_recommendation_report(
    recs: list[PitcherRecommendation] | PitcherRecommendation,
    path: Path | str,
    **kwargs,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_recommendation_report(recs, **kwargs), encoding="utf-8")
    return path


def _format_pitcher(rec: PitcherRecommendation) -> list[str]:
    lines = [
        f"## {rec.pitcher_name} (MLBAM {rec.pitcher_id})",
        "",
        f"- Pitches modeled: **{rec.n_pitches:,}**",
        f"- Arsenal: {', '.join(rec.arsenal)}",
        f"- Overall expected xwOBA: {_pct_xw(rec.overall_current_xwoba)} → "
        f"{_pct_xw(rec.overall_optimized_xwoba)} "
        f"(improvement **{_delta_xw(rec.expected_improvement_xwoba)}**)",
        f"- Overall expected RV/pitch: {rec.overall_current_rv:+.4f} → "
        f"{rec.overall_optimized_rv:+.4f} "
        f"({rec.expected_improvement_rv:+.4f})",
        "",
    ]

    # Highlight platoon segments first.
    platoon = [s for s in rec.segments if s.segment.startswith("vs ") and "|" not in s.segment]
    detail = [s for s in rec.segments if s not in platoon]

    if platoon:
        lines.append("### Platoon usage")
        lines.append("")
        for seg in platoon:
            lines.extend(_format_segment(seg))
            lines.append("")

    if detail:
        lines.append("### Count / situation detail")
        lines.append("")
        # Keep the most actionable count segments (largest |ΔxwOBA|).
        ranked = sorted(detail, key=lambda s: abs(s.expected_improvement_xwoba), reverse=True)
        for seg in ranked[:6]:
            lines.extend(_format_segment(seg, compact=True))
            lines.append("")

    if rec.pairing_notes:
        lines.append("### Arsenal pairing signals")
        lines.append("")
        for note in rec.pairing_notes:
            lines.append(f"- {note}")
        lines.append("")

    return lines


def _format_segment(seg: SegmentRecommendation, *, compact: bool = False) -> list[str]:
    header = f"#### {seg.segment}" if not compact else f"**{seg.segment}** ({seg.n_pitches} pitches)"
    lines = [
        header,
        "",
        f"Expected improvement: **{_delta_xw(seg.expected_improvement_xwoba)} xwOBA** "
        f"({seg.current_xwoba:.3f} → {seg.optimized_xwoba:.3f}); "
        f"n={seg.n_pitches}",
        "",
    ]
    # Show pitches with meaningful shifts.
    meaningful = [c for c in seg.changes if abs(c.delta_pct) >= 0.015]
    if not meaningful:
        meaningful = seg.changes[:3]
    for ch in meaningful:
        direction = "increase" if ch.delta_pct > 0 else "reduce"
        lines.append(
            f"- {direction.upper()} **{ch.pitch_type}** usage "
            f"from {_pct(ch.current_pct)} → {_pct(ch.recommended_pct)}"
        )
    return lines


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def _pct_xw(x: float) -> str:
    return f"{x:.3f}"


def _delta_xw(x: float) -> str:
    # Negative is good for pitcher.
    return f"{x:+.3f}"
