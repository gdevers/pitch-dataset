"""Step-2 pitch location recommendations: given a chosen pitch type, where should it go?

The situational type model deliberately ignores location (it is a pre-location decision).
This module trains a *separate* model that conditions on pitch type + shape + context +
a batter-relative location template and predicts run value, xwOBA, and whiff probability.

Location templates (batter-relative, so L/R both read naturally):

* 9 in-zone cells: ``{up,mid,down} × {in,mid,away}`` (center cell = ``heart``).
* 4 chase quadrants just off the zone: ``chase_{up,down}_{in,away}`` (Statcast 11–14 style).
* ``waste``: far off the plate / in the dirt; kept in training, never recommended.

Horizontal: ``x_away`` = ``plate_x`` flipped so positive is away from the batter.
Vertical: ``z_norm`` = ``(plate_z - sz_bot) / (sz_top - sz_bot)`` (0 = bottom, 1 = top).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.metrics import log_loss, mean_absolute_error, r2_score, roc_auc_score
from sklearn.model_selection import train_test_split

from pitch_dataset.arsenal import PITCH_ONEHOT_PREFIX, arsenal_pitch_types

DEFAULT_LOCATION_MODEL_PATH = Path("models/situational_location_model.joblib")

ZONE_HALF_WIDTH_FT = 0.83
CHASE_MAX_X_FT = 1.8
CHASE_MIN_Z_NORM = -0.9
CHASE_MAX_Z_NORM = 1.75
_X_THIRD = ZONE_HALF_WIDTH_FT / 3.0

LOC_ONEHOT_PREFIX = "loc_"

# (id, label, region, x_away center ft, z_norm center)
_ZONE_SPECS: list[tuple[str, str, str, float, float]] = [
    ("up_in", "Up & in", "zone", -2 * _X_THIRD, 5 / 6),
    ("up_mid", "Up, middle", "zone", 0.0, 5 / 6),
    ("up_away", "Up & away", "zone", 2 * _X_THIRD, 5 / 6),
    ("mid_in", "Middle in", "zone", -2 * _X_THIRD, 0.5),
    ("heart", "Heart", "zone", 0.0, 0.5),
    ("mid_away", "Middle away", "zone", 2 * _X_THIRD, 0.5),
    ("down_in", "Down & in", "zone", -2 * _X_THIRD, 1 / 6),
    ("down_mid", "Down, middle", "zone", 0.0, 1 / 6),
    ("down_away", "Down & away", "zone", 2 * _X_THIRD, 1 / 6),
    ("chase_up_in", "Chase up & in", "chase", -1.15, 1.25),
    ("chase_up_away", "Chase up & away", "chase", 1.15, 1.25),
    ("chase_down_in", "Chase down & in", "chase", -1.15, -0.3),
    ("chase_down_away", "Chase down & away", "chase", 1.15, -0.3),
    ("waste", "Waste", "waste", 0.0, 0.5),
]

LOCATION_ZONES: list[dict[str, Any]] = [
    {"id": z, "label": lbl, "region": reg, "x_center": x, "z_center": zc}
    for z, lbl, reg, x, zc in _ZONE_SPECS
]
ZONE_IDS: list[str] = [z["id"] for z in LOCATION_ZONES]
CANDIDATE_ZONE_IDS: list[str] = [z["id"] for z in LOCATION_ZONES if z["region"] != "waste"]
_ZONE_BY_ID = {z["id"]: z for z in LOCATION_ZONES}

BATTER_ZONE_PRIOR_COLS = ["batter_zone_xwoba_prior", "batter_zone_whiff_prior"]
# Pseudo-counts for empirical-Bayes shrinkage toward league zone means.
BATTER_ZONE_XWOBA_K = 40.0
BATTER_ZONE_WHIFF_K = 25.0

# League cell priors: pitch type × same-hand × zone × count, shrunk toward zone × count.
# Gives the trees the pitch/handedness/zone/count interaction directly (e.g. RHP slider to
# a LHH back foot) instead of relying on deep splits to discover it.
CELL_PRIOR_COLS = ["cell_rv_prior", "cell_whiff_prior"]
CELL_PRIOR_K = 150.0
# Ranking pulls a zone's RV toward the pitch's cross-zone mean by n / (n + K), where n is
# league pitches in that pitch type × same-hand × zone × count cell (rare cells are noisy).
SUPPORT_K = 100.0

PITCH_GROUPS = {
    "FF": "fastball", "SI": "fastball", "FC": "fastball", "FA": "fastball",
    "SL": "breaking", "ST": "breaking", "CU": "breaking", "KC": "breaking",
    "SV": "breaking", "CS": "breaking",
    "CH": "offspeed", "FS": "offspeed", "FO": "offspeed", "SC": "offspeed",
    "EP": "offspeed", "KN": "offspeed",
}


def pitch_group(pitch_type: str) -> str:
    return PITCH_GROUPS.get(str(pitch_type).upper(), "other")

LOCATION_GEOM_COLS = [
    "loc_x_center",
    "loc_z_center",
    "loc_in_zone",
    "loc_x_x_break_in",
    "loc_z_x_vbreak",
]

_SWING_DESCRIPTIONS = frozenset(
    {
        "swinging_strike",
        "swinging_strike_blocked",
        "foul",
        "foul_tip",
        "hit_into_play",
        "hit_into_play_score",
        "hit_into_play_no_out",
        "foul_bunt",
        "missed_bunt",
        "bunt_foul_tip",
    }
)
_WHIFF_DESCRIPTIONS = frozenset({"swinging_strike", "swinging_strike_blocked", "missed_bunt"})


def zone_label(zone_id: str) -> str:
    return _ZONE_BY_ID[zone_id]["label"]


def glove_side(*, p_throws: str, stand: str) -> str:
    """Which batter-relative side ('in' or 'away') is the pitcher's glove side."""
    same_hand = (p_throws or "R").upper() == (stand or "R").upper()
    return "away" if same_hand else "in"


def assign_location_zones(
    plate_x: pd.Series | np.ndarray,
    plate_z: pd.Series | np.ndarray,
    stand: pd.Series | np.ndarray,
    sz_top: pd.Series | np.ndarray | None = None,
    sz_bot: pd.Series | np.ndarray | None = None,
) -> pd.DataFrame:
    """Return ``x_away``, ``z_norm``, ``loc_zone`` for each pitch (NaN zone if no location)."""
    px = pd.to_numeric(pd.Series(plate_x), errors="coerce").to_numpy(dtype=float)
    pz = pd.to_numeric(pd.Series(plate_z), errors="coerce").to_numpy(dtype=float)
    st = pd.Series(stand).fillna("R").astype(str).str.upper().to_numpy()
    top = (
        pd.to_numeric(pd.Series(sz_top), errors="coerce").fillna(3.4).to_numpy(dtype=float)
        if sz_top is not None
        else np.full(len(px), 3.4)
    )
    bot = (
        pd.to_numeric(pd.Series(sz_bot), errors="coerce").fillna(1.6).to_numpy(dtype=float)
        if sz_bot is not None
        else np.full(len(px), 1.6)
    )
    height = np.where(top - bot > 0.5, top - bot, 1.8)
    x_away = np.where(st == "L", -px, px)
    z_norm = (pz - bot) / height

    col = np.where(x_away < -_X_THIRD, "in", np.where(x_away > _X_THIRD, "away", "mid"))
    row = np.where(z_norm > 2 / 3, "up", np.where(z_norm < 1 / 3, "down", "mid"))
    in_zone = (np.abs(x_away) <= ZONE_HALF_WIDTH_FT) & (z_norm >= 0) & (z_norm <= 1)
    waste = (
        (np.abs(x_away) > CHASE_MAX_X_FT)
        | (z_norm < CHASE_MIN_Z_NORM)
        | (z_norm > CHASE_MAX_Z_NORM)
    )
    chase_row = np.where(z_norm >= 0.5, "up", "down")
    chase_col = np.where(x_away >= 0, "away", "in")

    inner = np.char.add(np.char.add(row.astype(str), "_"), col.astype(str))
    inner = np.where(inner == "mid_mid", "heart", inner)
    chase = np.char.add(
        np.char.add(np.char.add("chase_", chase_row.astype(str)), "_"), chase_col.astype(str)
    )
    zone = np.where(in_zone, inner, np.where(waste, "waste", chase)).astype(object)
    missing = np.isnan(px) | np.isnan(pz)
    zone[missing] = None
    return pd.DataFrame({"x_away": x_away, "z_norm": z_norm, "loc_zone": zone})


def add_location_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    loc = assign_location_zones(
        out.get("plate_x"),
        out.get("plate_z"),
        out.get("stand", pd.Series("R", index=out.index)),
        out.get("sz_top"),
        out.get("sz_bot"),
    )
    loc.index = out.index
    out[["x_away", "z_norm", "loc_zone"]] = loc
    desc = out.get("description", pd.Series("", index=out.index)).fillna("")
    out["is_swing"] = desc.isin(_SWING_DESCRIPTIONS).astype(float)
    out["is_whiff"] = desc.isin(_WHIFF_DESCRIPTIONS).astype(float)
    return out


def league_zone_means(df: pd.DataFrame) -> pd.DataFrame:
    """League xwOBA per pitch and whiff-per-swing by zone (shrinkage targets)."""
    frame = df[df["loc_zone"].notna()]
    grp = frame.groupby("loc_zone")
    table = pd.DataFrame(
        {
            "xwoba": grp["target_xwoba"].mean(),
            "whiff": grp["is_whiff"].sum() / grp["is_swing"].sum().clip(lower=1),
            "n": grp.size(),
        }
    )
    return table.reindex(ZONE_IDS).fillna({"xwoba": 0.32, "whiff": 0.25, "n": 0})


def add_batter_zone_priors(df: pd.DataFrame, league: pd.DataFrame) -> pd.DataFrame:
    """Shifted (season-to-date, excluding current pitch) batter × zone priors with shrinkage."""
    out = df.copy()
    sort_cols = [
        c for c in ("game_date", "game_pk", "at_bat_number", "pitch_number") if c in out.columns
    ]
    ordered = out.sort_values(sort_cols) if sort_cols else out
    key = [ordered["batter"], ordered["loc_zone"].fillna("none")]
    xw = ordered["target_xwoba"].astype(float)
    sw = ordered["is_swing"].astype(float)
    wh = ordered["is_whiff"].astype(float)
    grp_xw = xw.groupby(key, sort=False)
    n_prev = grp_xw.cumcount().astype(float)
    xw_prev = grp_xw.cumsum() - xw
    sw_prev = sw.groupby(key, sort=False).cumsum() - sw
    wh_prev = wh.groupby(key, sort=False).cumsum() - wh

    lg_xw = ordered["loc_zone"].map(league["xwoba"]).fillna(0.32)
    lg_wh = ordered["loc_zone"].map(league["whiff"]).fillna(0.25)
    xw_prior = (xw_prev + BATTER_ZONE_XWOBA_K * lg_xw) / (n_prev + BATTER_ZONE_XWOBA_K)
    wh_prior = (wh_prev + BATTER_ZONE_WHIFF_K * lg_wh) / (sw_prev + BATTER_ZONE_WHIFF_K)
    out["batter_zone_xwoba_prior"] = xw_prior.reindex(out.index)
    out["batter_zone_whiff_prior"] = wh_prior.reindex(out.index)
    return out


def batter_zone_prior_table(batter_df: pd.DataFrame, league: pd.DataFrame) -> pd.DataFrame:
    """Full-sample batter × zone priors for inference (one row per zone id)."""
    table = pd.DataFrame(index=ZONE_IDS)
    lg_xw = league["xwoba"].reindex(ZONE_IDS).fillna(0.32)
    lg_wh = league["whiff"].reindex(ZONE_IDS).fillna(0.25)
    if batter_df.empty or "loc_zone" not in batter_df.columns:
        table["batter_zone_xwoba_prior"] = lg_xw
        table["batter_zone_whiff_prior"] = lg_wh
        table["n"] = 0
        return table
    grp = batter_df[batter_df["loc_zone"].notna()].groupby("loc_zone")
    n = grp.size().reindex(ZONE_IDS).fillna(0)
    xw_sum = grp["target_xwoba"].sum().reindex(ZONE_IDS).fillna(0)
    sw_sum = grp["is_swing"].sum().reindex(ZONE_IDS).fillna(0)
    wh_sum = grp["is_whiff"].sum().reindex(ZONE_IDS).fillna(0)
    table["batter_zone_xwoba_prior"] = (xw_sum + BATTER_ZONE_XWOBA_K * lg_xw) / (
        n + BATTER_ZONE_XWOBA_K
    )
    table["batter_zone_whiff_prior"] = (wh_sum + BATTER_ZONE_WHIFF_K * lg_wh) / (
        sw_sum + BATTER_ZONE_WHIFF_K
    )
    table["n"] = n
    return table


def _count_key(balls: Any, strikes: Any) -> pd.Series:
    b = pd.to_numeric(pd.Series(balls), errors="coerce").fillna(0).astype(int).astype(str)
    s = pd.to_numeric(pd.Series(strikes), errors="coerce").fillna(0).astype(int).astype(str)
    return (b + "-" + s).reset_index(drop=True)


def build_cell_prior_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Shrunk league RV / whiff-per-pitch tables for (pitch, same-hand, zone, count) cells.

    Hierarchy: zone × count → pitch group × same-hand × zone × count → pitch type cell.
    """
    frame = pd.DataFrame(
        {
            "pitch_type": df["pitch_type"].astype(str).to_numpy(),
            "group": df["pitch_type"].map(pitch_group).to_numpy(),
            "platoon_rh": pd.to_numeric(df["platoon_rh"], errors="coerce").fillna(0).astype(int).to_numpy(),
            "loc_zone": df["loc_zone"].to_numpy(),
            "count": _count_key(df["balls"], df["strikes"]).to_numpy(),
            "rv": df["target_rv"].astype(float).to_numpy(),
            "wh": df["is_whiff"].astype(float).to_numpy(),
        }
    ).dropna(subset=["loc_zone", "rv"])
    zc = frame.groupby(["loc_zone", "count"]).agg(rv=("rv", "mean"), wh=("wh", "mean"))

    def _shrink(keys: list[str], parent: pd.DataFrame, parent_keys: list[str]) -> pd.DataFrame:
        cell = frame.groupby(keys).agg(
            rv_sum=("rv", "sum"), wh_sum=("wh", "sum"), n=("rv", "size")
        )
        par = parent.reindex(
            pd.MultiIndex.from_frame(cell.index.to_frame(index=False)[parent_keys])
        )
        cell["rv"] = (cell["rv_sum"] + CELL_PRIOR_K * par["rv"].to_numpy()) / (
            cell["n"] + CELL_PRIOR_K
        )
        cell["wh"] = (cell["wh_sum"] + CELL_PRIOR_K * par["wh"].to_numpy()) / (
            cell["n"] + CELL_PRIOR_K
        )
        return cell[["rv", "wh", "n"]]

    grp = _shrink(["group", "platoon_rh", "loc_zone", "count"], zc, ["loc_zone", "count"])
    cell = _shrink(
        ["group", "pitch_type", "platoon_rh", "loc_zone", "count"],
        grp,
        ["group", "platoon_rh", "loc_zone", "count"],
    ).droplevel("group")
    return {"zc": zc, "group": grp, "cell": cell}


def apply_cell_priors(
    tables: dict[str, pd.DataFrame],
    *,
    pitch_type: Iterable[str],
    platoon_rh: Iterable[Any],
    zones: Iterable[str],
    balls: Iterable[Any],
    strikes: Iterable[Any],
) -> pd.DataFrame:
    count = _count_key(balls, strikes)
    zones = pd.Series(list(zones))
    pts = pd.Series(list(pitch_type)).astype(str)
    plat = pd.to_numeric(pd.Series(list(platoon_rh)), errors="coerce").fillna(0).astype(int)
    lookups = [
        tables["cell"].reindex(pd.MultiIndex.from_arrays([pts, plat, zones, count])),
        tables["group"].reindex(
            pd.MultiIndex.from_arrays([pts.map(pitch_group), plat, zones, count])
        ),
        tables["zc"].reindex(pd.MultiIndex.from_arrays([zones, count])),
    ]
    rv = np.full(len(zones), np.nan)
    wh = np.full(len(zones), np.nan)
    for tbl in lookups:
        rv = np.where(np.isnan(rv), tbl["rv"].to_numpy(), rv)
        wh = np.where(np.isnan(wh), tbl["wh"].to_numpy(), wh)
    return pd.DataFrame(
        {"cell_rv_prior": np.nan_to_num(rv, nan=0.0), "cell_whiff_prior": np.nan_to_num(wh, nan=0.1)}
    )


def _add_zone_features(X: pd.DataFrame, zones: pd.Series) -> pd.DataFrame:
    """One-hot + geometric zone features; ``X`` must already have shape columns."""
    out = X.copy()
    zones = zones.reset_index(drop=True)
    out = out.reset_index(drop=True)
    for zid in ZONE_IDS:
        out[f"{LOC_ONEHOT_PREFIX}{zid}"] = (zones == zid).astype(int).to_numpy()
    x_c = zones.map(lambda z: _ZONE_BY_ID[z]["x_center"]).astype(float).to_numpy()
    z_c = zones.map(lambda z: _ZONE_BY_ID[z]["z_center"]).astype(float).to_numpy()
    out["loc_x_center"] = x_c
    out["loc_z_center"] = z_c
    out["loc_in_zone"] = zones.map(lambda z: _ZONE_BY_ID[z]["region"] == "zone").astype(int).to_numpy()
    brk_in = pd.to_numeric(out.get("api_break_x_batter_in", 0.0), errors="coerce")
    vbrk = pd.to_numeric(out.get("api_break_z_with_gravity", 0.0), errors="coerce")
    out["loc_x_x_break_in"] = x_c * np.nan_to_num(np.asarray(brk_in, dtype=float))
    out["loc_z_x_vbreak"] = z_c * np.nan_to_num(np.asarray(vbrk, dtype=float))
    return out


@dataclass
class LocationScore:
    zone: str
    label: str
    region: str
    pred_rv: float
    pred_xwoba: float
    pred_whiff: float
    rank: int = 0
    batter_zone_xwoba: float | None = None
    pred_rv_raw: float | None = None
    support_n: int = 0


@dataclass
class LocationModel:
    """Run value + xwOBA regressors and whiff classifier over (context, pitch, zone)."""

    rv_model: HistGradientBoostingRegressor
    xwoba_model: HistGradientBoostingRegressor
    whiff_model: HistGradientBoostingClassifier
    feature_names: list[str]
    pitch_types: list[str]
    league_zone: pd.DataFrame
    cell_tables: dict[str, pd.DataFrame]
    meta: dict[str, Any] = field(default_factory=dict)

    def _X(self, X: pd.DataFrame) -> pd.DataFrame:
        aligned = X.copy()
        for name in self.feature_names:
            if name not in aligned.columns:
                aligned[name] = 0.0
        return aligned[self.feature_names].fillna(0.0)

    def predict(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        Xa = self._X(X)
        return (
            self.rv_model.predict(Xa),
            self.xwoba_model.predict(Xa),
            self.whiff_model.predict_proba(Xa)[:, 1],
        )

    def save(self, path: Path | str = DEFAULT_LOCATION_MODEL_PATH) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path, compress=3)
        return path


def load_location_model(path: Path | str = DEFAULT_LOCATION_MODEL_PATH) -> LocationModel:
    obj = joblib.load(path)
    if not isinstance(obj, LocationModel):
        raise TypeError(f"Expected LocationModel at {path}, got {type(obj)}")
    return obj


def prepare_location_pitches(prepared: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add zone columns + shifted batter zone priors to situational-prepared pitches."""
    if "loc_zone" in prepared.columns and "batter_zone_xwoba_prior" in prepared.columns:
        return prepared, league_zone_means(prepared)
    out = add_location_columns(prepared)
    league = league_zone_means(out)
    out = add_batter_zone_priors(out, league)
    return out, league


def build_location_matrix(
    frame: pd.DataFrame,
    *,
    pitch_types: Iterable[str],
    cell_tables: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """``frame`` must already be filtered to rows with ``target_rv`` and ``loc_zone``."""
    from pitch_dataset.situational import SITUATIONAL_CONTEXT_COLS

    X = frame[SITUATIONAL_CONTEXT_COLS + BATTER_ZONE_PRIOR_COLS].copy()
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    X = X.fillna(X.median(numeric_only=True))
    for pt in pitch_types:
        X[f"{PITCH_ONEHOT_PREFIX}{pt}"] = (frame["pitch_type"] == pt).astype(int)
    X = _add_zone_features(X, frame["loc_zone"])
    cells = apply_cell_priors(
        cell_tables,
        pitch_type=frame["pitch_type"],
        platoon_rh=frame["platoon_rh"],
        zones=frame["loc_zone"],
        balls=frame["balls"],
        strikes=frame["strikes"],
    )
    for col in CELL_PRIOR_COLS:
        X[col] = cells[col].to_numpy()
    return (
        X,
        frame["target_rv"].astype(float).reset_index(drop=True),
        frame["target_xwoba"].astype(float).reset_index(drop=True),
        frame["is_whiff"].astype(int).reset_index(drop=True),
    )


def train_location_model(
    pitches: pd.DataFrame,
    *,
    model_path: Path | str = DEFAULT_LOCATION_MODEL_PATH,
    data_dir: Path | str = "data",
    season: int | None = None,
    prepared: pd.DataFrame | None = None,
    test_size: float = 0.2,
    random_state: int = 42,
    min_pitch_n: int = 200,
) -> tuple[LocationModel, dict[str, Any]]:
    from pitch_dataset.situational import prepare_situational_pitches

    if prepared is None:
        prepared = prepare_situational_pitches(pitches, data_dir=data_dir, season=season)
    loc_df, league = prepare_location_pitches(prepared)
    pitch_types = arsenal_pitch_types(loc_df, min_n=min_pitch_n)

    frame = loc_df.dropna(subset=["target_rv", "loc_zone"]).reset_index(drop=True)
    idx_train, idx_test = train_test_split(
        np.arange(len(frame)), test_size=test_size, random_state=random_state
    )
    cell_tables = build_cell_prior_tables(frame.iloc[idx_train])
    X, y_rv, y_xw, y_wh = build_location_matrix(
        frame, pitch_types=pitch_types, cell_tables=cell_tables
    )
    X_tr, X_te = X.iloc[idx_train], X.iloc[idx_test]

    params: dict[str, Any] = {
        "max_depth": 7,
        "learning_rate": 0.08,
        "max_iter": 300,
        "l2_regularization": 0.1,
        "random_state": random_state,
    }
    logging.info("Training location models on %d pitches, %d features", len(X_tr), X.shape[1])
    rv_model = HistGradientBoostingRegressor(**params).fit(X_tr, y_rv.iloc[idx_train])
    xw_model = HistGradientBoostingRegressor(**params).fit(X_tr, y_xw.iloc[idx_train])
    wh_model = HistGradientBoostingClassifier(**params).fit(X_tr, y_wh.iloc[idx_train])

    rv_pred = rv_model.predict(X_te)
    xw_pred = xw_model.predict(X_te)
    wh_prob = wh_model.predict_proba(X_te)[:, 1]

    test = frame.iloc[idx_test]
    cells = pd.DataFrame(
        {
            "group": test["pitch_type"].map(pitch_group).to_numpy(),
            "platoon_rh": test["platoon_rh"].to_numpy(),
            "count": _count_key(test["balls"], test["strikes"]).to_numpy(),
            "zone": test["loc_zone"].to_numpy(),
            "pred": rv_pred,
            "actual": y_rv.iloc[idx_test].to_numpy(),
        }
    ).groupby(["group", "platoon_rh", "count", "zone"])
    cell_tbl = cells.agg(pred=("pred", "mean"), actual=("actual", "mean"), n=("pred", "size"))
    cell_tbl = cell_tbl[cell_tbl["n"] >= 50]
    cell_corr = float(np.corrcoef(cell_tbl["pred"], cell_tbl["actual"])[0, 1])
    metrics: dict[str, Any] = {
        "n_pitches": len(loc_df),
        "n_train": len(idx_train),
        "n_test": len(idx_test),
        "date_min": str(loc_df["game_date"].min().date()) if "game_date" in loc_df else None,
        "date_max": str(loc_df["game_date"].max().date()) if "game_date" in loc_df else None,
        "rv_mae": float(mean_absolute_error(y_rv.iloc[idx_test], rv_pred)),
        "rv_r2": float(r2_score(y_rv.iloc[idx_test], rv_pred)),
        "xwoba_mae": float(mean_absolute_error(y_xw.iloc[idx_test], xw_pred)),
        "xwoba_r2": float(r2_score(y_xw.iloc[idx_test], xw_pred)),
        "whiff_auc": float(roc_auc_score(y_wh.iloc[idx_test], wh_prob)),
        "whiff_logloss": float(log_loss(y_wh.iloc[idx_test], wh_prob)),
        "whiff_base_rate": float(y_wh.mean()),
        "heldout_cell_rv_corr": cell_corr,
        "heldout_cells_n50": len(cell_tbl),
        "pitch_types": pitch_types,
        "zones": ZONE_IDS,
        "zone_share": {
            z: float(v) for z, v in loc_df["loc_zone"].value_counts(normalize=True).items()
        },
    }
    model = LocationModel(
        rv_model=rv_model,
        xwoba_model=xw_model,
        whiff_model=wh_model,
        feature_names=list(X.columns),
        pitch_types=pitch_types,
        league_zone=league,
        cell_tables=cell_tables,
        meta=metrics,
    )
    model.save(model_path)
    return model, metrics


def score_locations(
    model: LocationModel,
    pitch_feature_rows: pd.DataFrame,
    pitch_types: list[str],
    batter_zone_priors: pd.DataFrame,
) -> dict[str, list[LocationScore]]:
    """Score every candidate zone for each pitch type row, best first.

    Ranked by support-adjusted run value (``pred_rv``); ``pred_rv_raw`` is the model output.

    ``pitch_feature_rows`` is the situational per-pitch-type feature frame (one row per
    entry in ``pitch_types``) already built for the type model.
    """
    n_z = len(CANDIDATE_ZONE_IDS)
    base = pitch_feature_rows.reset_index(drop=True)
    expanded = base.loc[base.index.repeat(n_z)].reset_index(drop=True)
    zones = pd.Series(CANDIDATE_ZONE_IDS * len(base))
    for col in BATTER_ZONE_PRIOR_COLS:
        expanded[col] = zones.map(batter_zone_priors[col]).astype(float).to_numpy()
    X = _add_zone_features(expanded, zones)
    cells = apply_cell_priors(
        model.cell_tables,
        pitch_type=np.repeat(pitch_types, n_z),
        platoon_rh=X["platoon_rh"],
        zones=zones,
        balls=X["balls"],
        strikes=X["strikes"],
    )
    for col in CELL_PRIOR_COLS:
        X[col] = cells[col].to_numpy()
    rv, xw, wh = model.predict(X)
    support = (
        model.cell_tables["cell"]["n"]
        .reindex(
            pd.MultiIndex.from_arrays(
                [
                    pd.Series(np.repeat(pitch_types, n_z)).astype(str),
                    pd.to_numeric(X["platoon_rh"], errors="coerce").fillna(0).astype(int),
                    zones,
                    _count_key(X["balls"], X["strikes"]),
                ]
            )
        )
        .fillna(0)
        .to_numpy()
    )

    out: dict[str, list[LocationScore]] = {}
    for i, pt in enumerate(pitch_types):
        sl = slice(i * n_z, (i + 1) * n_z)
        raw = rv[sl]
        w = support[sl] / (support[sl] + SUPPORT_K)
        adj = raw.mean() + w * (raw - raw.mean())
        scores = [
            LocationScore(
                zone=zid,
                label=zone_label(zid),
                region=_ZONE_BY_ID[zid]["region"],
                pred_rv=float(adj[j]),
                pred_xwoba=float(xw[sl][j]),
                pred_whiff=float(wh[sl][j]),
                batter_zone_xwoba=float(batter_zone_priors.loc[zid, "batter_zone_xwoba_prior"]),
                pred_rv_raw=float(raw[j]),
                support_n=int(support[sl][j]),
            )
            for j, zid in enumerate(CANDIDATE_ZONE_IDS)
        ]
        scores.sort(key=lambda s: s.pred_rv)
        for r, s in enumerate(scores, start=1):
            s.rank = r
        out[pt] = scores
    return out


def location_scores_to_dict(scores: list[LocationScore]) -> list[dict[str, Any]]:
    return [
        {
            "zone": s.zone,
            "label": s.label,
            "region": s.region,
            "rank": s.rank,
            "pred_rv": s.pred_rv,
            "pred_xwoba": s.pred_xwoba,
            "pred_whiff": s.pred_whiff,
            "batter_zone_xwoba": s.batter_zone_xwoba,
            "pred_rv_raw": s.pred_rv_raw,
            "support_n": s.support_n,
        }
        for s in scores
    ]


def format_location_text(
    pitch_type: str,
    scores: list[LocationScore],
    *,
    glove: str,
    top_n: int = 5,
) -> str:
    """Plain-text top-N locations; RV shown as runs saved per 100 pitches (pitcher view)."""
    arm = "away" if glove == "in" else "in"
    lines = [
        f"Top locations for {pitch_type} (batter-relative; glove side = {glove}, arm side = {arm}):"
    ]
    def _line(s: LocationScore) -> str:
        return (
            f"{s.rank:>2}. {s.label:<18} runs saved/100 {-100 * s.pred_rv:+5.2f} | "
            f"xwOBA {s.pred_xwoba:.3f} | whiff {100 * s.pred_whiff:4.1f}% | "
            f"league n={s.support_n}"
        )

    for s in scores[:top_n]:
        lines.append("  " + _line(s))
    heart = next((s for s in scores if s.zone == "heart"), None)
    if heart is not None and heart.rank > top_n:
        lines.append(f"  ({_line(heart)})")
    return "\n".join(lines)
