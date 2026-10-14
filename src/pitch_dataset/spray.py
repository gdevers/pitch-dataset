"""Pitch-to-field: where a hitter's contact goes for a given pitch type and location.

Batted balls are binned on a polar grid (spray angle × distance) split into ground balls
and air balls (line drives, fly balls, popups). Hitter × pitch type × zone samples are tiny,
so each distribution is a hierarchical blend:

    posterior = (own_counts + K · prior) / (n_own + K)

where ``prior`` is the league distribution for the same batter side × pitch type × zone,
re-weighted by the hitter's overall direction / ground-ball tendencies (shrunk ratios of
his all-pitch spray to the league all-pitch spray). ``n_own / (n_own + K)`` is reported as
the hitter-specific blend weight.

Coordinates: Statcast ``hc_x`` / ``hc_y`` are image pixels with home plate near
(125.42, 198.27). ``feet = 2.49 × pixels`` (checked against ``hit_distance_sc``: median
ratio 2.48 on home runs, 2.49 on fly outs). ``x_ft`` > 0 is the right-field side;
spray angle is measured from straight-away center (−45° = LF line, +45° = RF line).
For ground balls the coordinate is where the ball was *fielded*, not where it landed.
"""

from __future__ import annotations

import html
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pitch_dataset.location import (
    LOCATION_ZONES,
    ZONE_IDS,
    assign_location_zones,
    zone_label,
)
from pitch_dataset.storage import pitch_path

log = logging.getLogger(__name__)

HC_HOME_X = 125.42
HC_HOME_Y = 198.27
FT_PER_HC_UNIT = 2.49

SEASON_WEIGHTS: dict[int, float] = {2025: 0.7, 2026: 1.0}
DEFAULT_SPRAY_SEASONS = (2025, 2026)

ANGLE_EDGES = np.linspace(-45.0, 45.0, 13)  # 7.5° bins; pull/center/oppo thirds at ±15°
DIST_EDGES = np.array([0.0, 90.0, 150.0, 200.0, 250.0, 300.0, 350.0, 450.0])
N_ANG = len(ANGLE_EDGES) - 1
N_RING = len(DIST_EDGES) - 1
N_CELL = N_ANG * N_RING
GROUPS = ("ground", "air")
VEC_LEN = len(GROUPS) * N_CELL  # index = group * N_CELL + ring * N_ANG + angle

BB_TYPES = ["ground_ball", "line_drive", "fly_ball", "popup"]
BB_SHORT = {"ground_ball": "GB", "line_drive": "LD", "fly_ball": "FB", "popup": "PU"}

SPRAY_PITCH_TYPES = ["FF", "SI", "FC", "SL", "ST", "CU", "CH", "FS"]
_PITCH_TYPE_MAP = {
    **{pt: pt for pt in SPRAY_PITCH_TYPES},
    "FA": "FF", "KC": "CU", "SV": "CU", "CS": "CU", "FO": "FS", "SC": "CH",
}
PITCH_TYPE_NAMES = {
    "FF": "4-seam fastball", "SI": "Sinker", "FC": "Cutter", "SL": "Slider",
    "ST": "Sweeper", "CU": "Curveball", "CH": "Changeup", "FS": "Splitter",
}

# 15° lanes (2 angle bins each), field left → right.
LANES_GROUND = [
    "to the left side near the line", "to the left side (3B–SS)", "left of the 2B bag",
    "right of the 2B bag", "to the right side (2B–1B)", "to the right side near the line",
]
LANES_AIR = ["LF line", "left field", "left-center", "right-center", "right field", "RF line"]
N_LANE = len(LANES_GROUND)

# Generic park: (spray angle °, wall distance ft).
WALL_POINTS = [(-45.0, 330.0), (-22.5, 380.0), (0.0, 400.0), (22.5, 380.0), (45.0, 330.0)]

# Pseudo-counts (season-weighted batted balls / pitches).
SPRAY_K = 25.0  # hitter pitch × zone spray vs tendency-adjusted league prior
TENDENCY_K = 60.0  # hitter overall direction / GB ratios vs league overall
SWING_K = 40.0  # hitter pitch × zone swing / whiff rates
RARE_CELL_N = 30.0  # league balls in play below which a pitch × zone cell is flagged as noise

_HIT_EVENTS = frozenset({"single", "double", "triple", "home_run"})
_SWING = frozenset({
    "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play",
    "foul_bunt", "missed_bunt", "bunt_foul_tip",
})
_WHIFF = frozenset({"swinging_strike", "swinging_strike_blocked", "missed_bunt", "foul_tip"})
_FOUL = frozenset({"foul", "foul_bunt", "bunt_foul_tip"})

_ZONE_IDX = {z: i for i, z in enumerate(ZONE_IDS)}
_PT_IDX = {pt: i for i, pt in enumerate(SPRAY_PITCH_TYPES)}
_STAND_IDX = {"L": 0, "R": 1}

_PITCH_COLS = [
    "game_date", "batter", "stand", "pitch_type", "plate_x", "plate_z", "sz_top", "sz_bot",
    "description", "type", "bb_type", "events", "hc_x", "hc_y", "launch_speed",
    "launch_angle", "estimated_woba_using_speedangle", "pitcher", "p_throws", "balls",
    "strikes", "hit_distance_sc", "if_fielding_alignment", "of_fielding_alignment",
    "game_pk", "at_bat_number",
]

# Count "atoms" (non-overlapping) so any filter below is a union of atoms.
# 0: pitcher ahead, 2 strikes (0-2, 1-2)   1: pitcher ahead (0-1)
# 2: even, 2 strikes (2-2)                 3: even (0-0, 1-1)
# 4: pitcher behind, 2 strikes (3-2)       5: pitcher behind (1-0, 2-0, 3-0, 2-1, 3-1)
N_ATOM = 6
COUNT_FILTERS: dict[str, tuple[int, ...]] = {
    "all": tuple(range(N_ATOM)),
    "ahead": (0, 1),
    "even": (2, 3),
    "behind": (4, 5),
    "two_strike": (0, 2, 4),
}
COUNT_FILTER_LABELS = {
    "all": "all counts",
    "ahead": "pitcher ahead (0-1, 0-2, 1-2)",
    "even": "even counts (0-0, 1-1, 2-2)",
    "behind": "pitcher behind (1-0, 2-0, 3-0, 2-1, 3-1, 3-2)",
    "two_strike": "two-strike counts",
}
HAND_FILTERS: dict[str, tuple[int, ...]] = {"all": (0, 1), "L": (0,), "R": (1,)}
HAND_FILTER_LABELS = {"all": "both pitcher hands", "L": "vs LHP", "R": "vs RHP"}
FILTER_LEAGUE_K = 200.0  # smoothing of league count / hand ratios (season-weighted balls)
_OUT_EVENTS = frozenset({
    "field_out", "force_out", "grounded_into_double_play", "double_play", "sac_fly",
    "fielders_choice_out", "sac_bunt", "triple_play", "sac_fly_double_play",
    "sac_bunt_double_play",
})


def count_atom(balls: Any, strikes: Any) -> np.ndarray:
    b = pd.to_numeric(pd.Series(balls), errors="coerce").fillna(0).to_numpy()
    s = pd.to_numeric(pd.Series(strikes), errors="coerce").fillna(0).to_numpy()
    base = np.where(s > b, 0, np.where(s == b, 2, 4))
    return base + (s < 2).astype(int)

DEMO_HITTERS = [
    "Rafael Devers", "Aaron Judge", "Shohei Ohtani", "Kyle Schwarber", "Juan Soto",
    "Luis Arraez", "Isaac Paredes", "Jose Ramirez", "Bobby Witt", "Cal Raleigh",
    "Steven Kwan", "Pete Alonso",
]
DEMO_MATCHUP_PITCHERS = [
    "Dylan Cease", "Tarik Skubal", "Paul Skenes", "Kevin Gausman", "José Soriano",
    "Casey Mize", "Freddy Peralta", "Zack Wheeler", "Garrett Crochet", "Logan Webb",
]


def hc_to_feet(hc_x: Any, hc_y: Any) -> tuple[np.ndarray, np.ndarray]:
    """Statcast hit coordinates → feet from home plate (x: +RF side, y: toward CF)."""
    hx = pd.to_numeric(pd.Series(hc_x), errors="coerce").to_numpy(dtype=float)
    hy = pd.to_numeric(pd.Series(hc_y), errors="coerce").to_numpy(dtype=float)
    return FT_PER_HC_UNIT * (hx - HC_HOME_X), FT_PER_HC_UNIT * (HC_HOME_Y - hy)


def spray_angle(x_ft: np.ndarray, y_ft: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan2(x_ft, y_ft))


def wall_distance(angle_deg: float) -> float:
    """Generic-park wall: 330 ft at the poles, ~380 ft in the gaps, 400 ft to center."""
    a = np.radians(float(np.clip(angle_deg, -45.0, 45.0)))
    return 330.0 + 70.0 * np.cos(2 * a)


def field_geometry() -> dict[str, Any]:
    return {
        "angle_edges": ANGLE_EDGES.tolist(),
        "dist_edges": DIST_EDGES.tolist(),
        "n_ang": N_ANG,
        "n_ring": N_RING,
        "groups": list(GROUPS),
        "wall": [[float(a), round(wall_distance(a), 1)] for a in np.arange(-45.0, 45.01, 1.5)],
        "wall_labels": [[a, d] for a, d in WALL_POINTS],
        "lanes_ground": LANES_GROUND,
        "lanes_air": LANES_AIR,
        "ft_per_hc_unit": FT_PER_HC_UNIT,
        "hc_home": [HC_HOME_X, HC_HOME_Y],
    }


def _cell_index(angle: np.ndarray, dist: np.ndarray, is_air: np.ndarray) -> np.ndarray:
    a = np.clip(np.digitize(angle, ANGLE_EDGES) - 1, 0, N_ANG - 1)
    r = np.clip(np.digitize(dist, DIST_EDGES) - 1, 0, N_RING - 1)
    return is_air.astype(int) * N_CELL + r * N_ANG + a


def load_spray_pitches(
    data_dir: Path | str = "data",
    seasons: tuple[int, ...] | list[int] = DEFAULT_SPRAY_SEASONS,
    league: str = "mlb",
) -> pd.DataFrame:
    """Pitch rows with batter-relative zone, canonical pitch type, and season weight."""
    frames = []
    for season in seasons:
        path = pitch_path(data_dir, season=season, league=league)
        if not path.exists():
            log.warning("Spray: missing %s, skipping season %s", path, season)
            continue
        df = pd.read_parquet(path, columns=_PITCH_COLS)
        df["w"] = SEASON_WEIGHTS.get(int(season), 1.0)
        df["season"] = int(season)
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No pitch parquet files for seasons {seasons} in {data_dir}")
    df = pd.concat(frames, ignore_index=True)
    df["pt"] = df["pitch_type"].map(_PITCH_TYPE_MAP)
    df = df[df["pt"].notna() & df["stand"].isin(["L", "R"])].reset_index(drop=True)
    loc = assign_location_zones(df["plate_x"], df["plate_z"], df["stand"], df["sz_top"], df["sz_bot"])
    df["loc_zone"] = loc["loc_zone"].to_numpy()
    df = df[df["loc_zone"].notna()].reset_index(drop=True)
    return df


@dataclass
class SprayModel:
    """League tables + compact per-pitch frames for on-demand hitter profiles."""

    bip: pd.DataFrame
    swings: pd.DataFrame
    league_cells: np.ndarray  # (stand, pt, zone, VEC_LEN) weighted counts
    league_bb: np.ndarray  # (stand, pt, zone, 4)
    league_ev: np.ndarray  # (stand, pt, zone, 2) [sum, n]
    league_xw: np.ndarray  # (stand, pt, zone, 2)
    league_swing: np.ndarray  # (stand, pt, zone, 5) [n, swing, whiff, foul, in_play]
    cell_xwoba: np.ndarray  # (stand, VEC_LEN)
    cell_hit: np.ndarray  # (stand, VEC_LEN)
    cell_n: np.ndarray  # (stand, VEC_LEN)
    seasons: list[int]
    date_range: tuple[str, str]
    # League aggregates by (stand, pt, count atom, pitcher hand, ...) for count / hand filters.
    lg_ang: np.ndarray | None = None  # (..., group, angle) weighted balls
    lg_bb: np.ndarray | None = None  # (..., 4)
    lg_ev: np.ndarray | None = None  # (..., 2) [sum, n]
    lg_xw: np.ndarray | None = None  # (..., 2)
    lg_sw: np.ndarray | None = None  # (..., 5) [n, swing, whiff, foul, in_play]
    pitch_mix: pd.DataFrame | None = None  # pitcher × stand × atom × pt × zone weighted pitches
    pitchers: pd.DataFrame | None = None  # pitcher, p_throws, n
    align: pd.DataFrame | None = None  # batter × stand × IF / OF alignment label weights
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def league_overall_cells(self) -> np.ndarray:
        return self.league_cells.sum(axis=(1, 2))

    @property
    def league_overall_bb(self) -> np.ndarray:
        return self.league_bb.sum(axis=(1, 2))


def build_spray_model(
    data_dir: Path | str = "data",
    seasons: tuple[int, ...] | list[int] = DEFAULT_SPRAY_SEASONS,
    league: str = "mlb",
    pitches: pd.DataFrame | None = None,
) -> SprayModel:
    df = pitches if pitches is not None else load_spray_pitches(data_dir, seasons, league)
    s_idx = df["stand"].map(_STAND_IDX).to_numpy()
    p_idx = df["pt"].map(_PT_IDX).to_numpy()
    z_idx = df["loc_zone"].map(_ZONE_IDX).to_numpy()
    w = df["w"].to_numpy(dtype=float)
    desc = df["description"].fillna("")
    is_swing = desc.isin(_SWING).to_numpy()
    is_whiff = desc.isin(_WHIFF).to_numpy()
    is_foul = desc.isin(_FOUL).to_numpy()
    in_play = (df["type"] == "X").to_numpy()
    atom = count_atom(df["balls"], df["strikes"])
    ph_idx = (df["p_throws"] == "R").astype(int).to_numpy()

    shape = (2, len(SPRAY_PITCH_TYPES), len(ZONE_IDS))
    league_swing = np.zeros(shape + (5,))
    fshape = (2, len(SPRAY_PITCH_TYPES), N_ATOM, 2)
    lg_sw = np.zeros(fshape + (5,))
    for k, flag in enumerate([np.ones(len(df), bool), is_swing, is_whiff, is_foul, in_play]):
        np.add.at(league_swing[..., k], (s_idx, p_idx, z_idx), w * flag)
        np.add.at(lg_sw[..., k], (s_idx, p_idx, atom, ph_idx), w * flag)

    swings = pd.DataFrame(
        {
            "batter": df["batter"].astype(int).to_numpy(),
            "s": s_idx, "p": p_idx, "z": z_idx, "k": atom, "ph": ph_idx,
            "n": w, "swing": w * is_swing, "whiff": w * is_whiff,
            "foul": w * is_foul, "in_play": w * in_play, "cnt": 1,
        }
    ).groupby(["batter", "s", "p", "z", "k", "ph"], as_index=False).sum()

    pitchers = (
        pd.DataFrame({"pitcher": df["pitcher"].astype(int).to_numpy(), "ph": ph_idx, "w": w})
        .groupby("pitcher")
        .agg(n=("w", "size"), r_share=("ph", "mean"))
        .reset_index()
    )
    pitchers["p_throws"] = np.where(pitchers["r_share"] >= 0.5, "R", "L")
    pitch_mix = (
        pd.DataFrame({
            "pitcher": df["pitcher"].astype(int).to_numpy(),
            "s": s_idx, "k": atom, "p": p_idx, "z": z_idx, "w": w,
        })
        .groupby(["pitcher", "s", "k", "p", "z"], as_index=False)["w"].sum()
    )
    align = (
        pd.DataFrame({
            "batter": df["batter"].astype(int).to_numpy(), "s": s_idx,
            "if_al": df["if_fielding_alignment"].fillna("Unknown").astype(str).to_numpy(),
            "of_al": df["of_fielding_alignment"].fillna("Unknown").astype(str).to_numpy(),
            "w": w,
        })
        .groupby(["batter", "s", "if_al", "of_al"], as_index=False)["w"].sum()
    )

    bip_mask = in_play & df["hc_x"].notna().to_numpy() & df["bb_type"].isin(BB_TYPES).to_numpy()
    b = df[bip_mask].reset_index(drop=True)
    x_ft, y_ft = hc_to_feet(b["hc_x"], b["hc_y"])
    ang = spray_angle(x_ft, y_ft)
    dist = np.hypot(x_ft, y_ft)
    is_air = (b["bb_type"] != "ground_ball").to_numpy()
    bip = pd.DataFrame(
        {
            "batter": b["batter"].astype(int).to_numpy(),
            "s": b["stand"].map(_STAND_IDX).to_numpy(),
            "p": b["pt"].map(_PT_IDX).to_numpy(),
            "z": b["loc_zone"].map(_ZONE_IDX).to_numpy(),
            "cell": _cell_index(ang, dist, is_air),
            "bb": b["bb_type"].map({t: i for i, t in enumerate(BB_TYPES)}).to_numpy(),
            "ev": pd.to_numeric(b["launch_speed"], errors="coerce").to_numpy(),
            "la": pd.to_numeric(b["launch_angle"], errors="coerce").to_numpy(),
            "xw": pd.to_numeric(b["estimated_woba_using_speedangle"], errors="coerce").to_numpy(),
            "hit": b["events"].isin(_HIT_EVENTS).to_numpy(),
            "w": b["w"].to_numpy(dtype=float),
            "x_ft": x_ft, "y_ft": y_ft, "angle": ang,
            "date": pd.to_datetime(b["game_date"]).dt.strftime("%Y-%m-%d").to_numpy(),
            "events": b["events"].fillna("").astype(str).to_numpy(),
            "k": atom[bip_mask],
            "ph": ph_idx[bip_mask],
            "pitcher": b["pitcher"].astype(int).to_numpy(),
            "dist": pd.to_numeric(b["hit_distance_sc"], errors="coerce").to_numpy(),
            "game_pk": pd.to_numeric(b["game_pk"], errors="coerce").fillna(0).astype(int).to_numpy(),
            "ab": pd.to_numeric(b["at_bat_number"], errors="coerce").fillna(0).astype(int).to_numpy(),
        }
    )

    key = (bip["s"].to_numpy(), bip["p"].to_numpy(), bip["z"].to_numpy())
    bw = bip["w"].to_numpy()
    fkey = (bip["s"].to_numpy(), bip["p"].to_numpy(), bip["k"].to_numpy(), bip["ph"].to_numpy())
    lg_ang = np.zeros(fshape + (len(GROUPS), N_ANG))
    cell = bip["cell"].to_numpy()
    np.add.at(lg_ang, fkey + (cell // N_CELL, cell % N_ANG), bw)
    lg_bb = np.zeros(fshape + (len(BB_TYPES),))
    np.add.at(lg_bb, fkey + (bip["bb"].to_numpy(),), bw)
    lg_ev = np.zeros(fshape + (2,))
    lg_xw = np.zeros(fshape + (2,))
    for arr, col in ((lg_ev, "ev"), (lg_xw, "xw")):
        v = bip[col].to_numpy()
        ok = ~np.isnan(v)
        np.add.at(arr[..., 0], tuple(k[ok] for k in fkey), bw[ok] * v[ok])
        np.add.at(arr[..., 1], tuple(k[ok] for k in fkey), bw[ok])
    league_cells = np.zeros(shape + (VEC_LEN,))
    np.add.at(league_cells, key + (bip["cell"].to_numpy(),), bw)
    league_bb = np.zeros(shape + (len(BB_TYPES),))
    np.add.at(league_bb, key + (bip["bb"].to_numpy(),), bw)
    league_ev = np.zeros(shape + (2,))
    league_xw = np.zeros(shape + (2,))
    for arr, col in ((league_ev, "ev"), (league_xw, "xw")):
        v = bip[col].to_numpy()
        ok = ~np.isnan(v)
        np.add.at(arr[..., 0], tuple(k[ok] for k in key), bw[ok] * v[ok])
        np.add.at(arr[..., 1], tuple(k[ok] for k in key), bw[ok])

    cell_n = np.zeros((2, VEC_LEN))
    cell_xw = np.zeros((2, VEC_LEN))
    cell_hit = np.zeros((2, VEC_LEN))
    xw = bip["xw"].fillna(0).to_numpy()
    np.add.at(cell_n, (bip["s"], bip["cell"]), bw)
    np.add.at(cell_xw, (bip["s"], bip["cell"]), bw * xw)
    np.add.at(cell_hit, (bip["s"], bip["cell"]), bw * bip["hit"].to_numpy())
    with np.errstate(invalid="ignore", divide="ignore"):
        cell_xwoba = np.where(cell_n > 0, cell_xw / cell_n, np.nan)
        cell_hit_rate = np.where(cell_n > 0, cell_hit / cell_n, np.nan)

    dates = pd.to_datetime(df["game_date"])
    model = SprayModel(
        bip=bip,
        swings=swings,
        league_cells=league_cells,
        league_bb=league_bb,
        league_ev=league_ev,
        league_xw=league_xw,
        league_swing=league_swing,
        cell_xwoba=cell_xwoba,
        cell_hit=cell_hit_rate,
        cell_n=cell_n,
        seasons=sorted(int(s) for s in df["season"].unique()) if "season" in df else [],
        date_range=(str(dates.min().date()), str(dates.max().date())),
        lg_ang=lg_ang,
        lg_bb=lg_bb,
        lg_ev=lg_ev,
        lg_xw=lg_xw,
        lg_sw=lg_sw,
        pitch_mix=pitch_mix,
        pitchers=pitchers,
        align=align,
        meta={"n_pitches": len(df), "n_bip": len(bip)},
    )
    log.info("Spray model: %d pitches, %d batted balls", len(df), len(bip))
    return model


def _norm(v: np.ndarray) -> np.ndarray:
    s = v.sum()
    return v / s if s > 0 else np.full_like(v, 1.0 / len(v))


def _lane_of_angle_bins() -> np.ndarray:
    return np.arange(N_ANG) // (N_ANG // N_LANE)


def _angle_marginal(vec: np.ndarray) -> np.ndarray:
    """(group, angle) totals from a VEC_LEN vector."""
    return vec.reshape(len(GROUPS), N_RING, N_ANG).sum(axis=1)


def _tendency_ratio(own_vec: np.ndarray, league_vec: np.ndarray) -> tuple[np.ndarray, float]:
    """Shrunk hitter/league ratio over (group × angle) — direction + ground/air tendency."""
    n_own = own_vec.sum()
    lg = _norm(_angle_marginal(league_vec))
    own = _angle_marginal(own_vec)
    p_h = (own + TENDENCY_K * lg) / (n_own + TENDENCY_K)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(lg > 0, p_h / lg, 1.0)
    return ratio, float(n_own)


def _batter_frames(model: SprayModel, batter_id: int, stand: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    s = _STAND_IDX[stand]
    bip = model.bip[(model.bip["batter"] == batter_id) & (model.bip["s"] == s)]
    sw = model.swings[(model.swings["batter"] == batter_id) & (model.swings["s"] == s)]
    return bip, sw


def batter_stands(model: SprayModel, batter_id: int) -> dict[str, float]:
    """Season-weighted pitches seen per batter side (switch hitters have both)."""
    sw = model.swings[model.swings["batter"] == batter_id]
    out = sw.groupby("s")["n"].sum()
    inv = {v: k for k, v in _STAND_IDX.items()}
    return {inv[int(k)]: float(v) for k, v in out.items()}


def _pull_center_oppo(vec: np.ndarray, stand: str) -> dict[str, float]:
    ang = _norm(vec.reshape(len(GROUPS), N_RING, N_ANG).sum(axis=(0, 1)))
    third = N_ANG // 3
    left, mid, right = ang[:third].sum(), ang[third : 2 * third].sum(), ang[2 * third :].sum()
    pull, oppo = (left, right) if stand == "R" else (right, left)
    return {"pull": float(pull), "center": float(mid), "oppo": float(oppo)}


def _lanes(vec: np.ndarray, group: int) -> np.ndarray:
    part = vec.reshape(len(GROUPS), N_RING, N_ANG)[group].sum(axis=0)
    return np.bincount(_lane_of_angle_bins(), weights=part, minlength=N_LANE)


def _zone_entry(
    model: SprayModel,
    *,
    stand: str,
    pt_i: int,
    z_i: int,
    own_bip: pd.DataFrame | None,
    own_sw: pd.DataFrame | None,
    ratio: np.ndarray | None,
    bb_ratio: np.ndarray | None,
    ev_shift: float,
    xw_shift: float,
    swing_ratio: np.ndarray | None,
) -> dict[str, Any]:
    s = _STAND_IDX[stand]
    lg_cells = model.league_cells[s, pt_i, z_i]
    lg_n = float(lg_cells.sum())
    lg_dist = _norm(lg_cells)
    prior = lg_dist.copy()
    if ratio is not None:
        prior = _norm((lg_dist.reshape(len(GROUPS), N_RING, N_ANG) * ratio[:, None, :]).ravel())

    own_vec = np.zeros(VEC_LEN)
    own_bb = np.zeros(len(BB_TYPES))
    own_ev = own_xw = (0.0, 0.0)
    n_own_raw = 0
    if own_bip is not None and not own_bip.empty:
        np.add.at(own_vec, own_bip["cell"].to_numpy(), own_bip["w"].to_numpy())
        np.add.at(own_bb, own_bip["bb"].to_numpy(), own_bip["w"].to_numpy())
        ev_ok = own_bip["ev"].notna()
        xw_ok = own_bip["xw"].notna()
        own_ev = (float((own_bip["ev"][ev_ok] * own_bip["w"][ev_ok]).sum()), float(own_bip["w"][ev_ok].sum()))
        own_xw = (float((own_bip["xw"][xw_ok] * own_bip["w"][xw_ok]).sum()), float(own_bip["w"][xw_ok].sum()))
        n_own_raw = len(own_bip)
    n_own = float(own_vec.sum())
    weight = n_own / (n_own + SPRAY_K) if ratio is not None else 0.0
    post = (own_vec + SPRAY_K * prior) / (n_own + SPRAY_K) if ratio is not None else lg_dist

    lg_bb = _norm(model.league_bb[s, pt_i, z_i])
    bb_prior = _norm(lg_bb * bb_ratio) if bb_ratio is not None else lg_bb
    bb_post = (own_bb + SPRAY_K * bb_prior) / (own_bb.sum() + SPRAY_K) if ratio is not None else lg_bb

    ev_sum, ev_n = model.league_ev[s, pt_i, z_i]
    xw_sum, xw_n = model.league_xw[s, pt_i, z_i]
    lg_ev = ev_sum / ev_n if ev_n else float("nan")
    lg_xw = xw_sum / xw_n if xw_n else float("nan")
    ev_post = (own_ev[0] + SPRAY_K * (lg_ev + ev_shift)) / (own_ev[1] + SPRAY_K)
    xw_post = (own_xw[0] + SPRAY_K * (lg_xw + xw_shift)) / (own_xw[1] + SPRAY_K)

    lg_sw = model.league_swing[s, pt_i, z_i]
    lg_rates = {
        "swing": lg_sw[1] / max(lg_sw[0], 1e-9),
        "whiff": lg_sw[2] / max(lg_sw[1], 1e-9),
        "foul": lg_sw[3] / max(lg_sw[1], 1e-9),
        "in_play": lg_sw[4] / max(lg_sw[1], 1e-9),
    }
    own_sw_arr = np.zeros(5)
    own_cnt = 0
    if own_sw is not None and not own_sw.empty:
        own_sw_arr = own_sw[["n", "swing", "whiff", "foul", "in_play"]].sum().to_numpy(dtype=float)
        own_cnt = int(own_sw["cnt"].sum())
    sr = swing_ratio if swing_ratio is not None else np.ones(4)
    p_swing = min(lg_rates["swing"] * sr[0], 0.99)
    p_whiff = min(lg_rates["whiff"] * sr[1], 0.99)
    p_foul = min(lg_rates["foul"] * sr[2], 0.99)
    p_ip = min(lg_rates["in_play"] * sr[3], 0.99)
    swing_post = (own_sw_arr[1] + SWING_K * p_swing) / (own_sw_arr[0] + SWING_K)
    whiff_post = (own_sw_arr[2] + SWING_K * p_whiff) / (own_sw_arr[1] + SWING_K)
    foul_post = (own_sw_arr[3] + SWING_K * p_foul) / (own_sw_arr[1] + SWING_K)
    ip_post = (own_sw_arr[4] + SWING_K * p_ip) / (own_sw_arr[1] + SWING_K)

    cells_xw = model.cell_xwoba[s]
    exp_hit = float(np.nansum(post * np.nan_to_num(model.cell_hit[s])))
    return {
        "zone": ZONE_IDS[z_i],
        "label": zone_label(ZONE_IDS[z_i]),
        "cells": post,
        "league_cells": lg_dist,
        "bb": dict(zip(BB_TYPES, bb_post.tolist(), strict=True)),
        "league_bb": dict(zip(BB_TYPES, lg_bb.tolist(), strict=True)),
        "ev": float(ev_post),
        "league_ev": float(lg_ev),
        "xwoba_con": float(xw_post),
        "league_xwoba_con": float(lg_xw),
        "hit_rate_from_spots": exp_hit,
        "landing_xwoba": float(np.nansum(post * np.nan_to_num(cells_xw))),
        "direction": _pull_center_oppo(post, stand),
        "league_direction": _pull_center_oppo(lg_dist, stand),
        "lanes_ground": _lanes(post, 0).tolist(),
        "lanes_air": _lanes(post, 1).tolist(),
        "league_lanes_ground": _lanes(lg_dist, 0).tolist(),
        "league_lanes_air": _lanes(lg_dist, 1).tolist(),
        "swing": {
            "swing_rate": float(swing_post),
            "whiff_per_swing": float(whiff_post),
            "foul_per_swing": float(foul_post),
            "in_play_per_swing": float(ip_post),
            "league_swing_rate": float(lg_rates["swing"]),
            "league_whiff_per_swing": float(lg_rates["whiff"]),
            "own_pitches": own_cnt,
        },
        "n_own_bip": n_own_raw,
        "n_own_weighted": round(n_own, 1),
        "n_league_bip": round(lg_n, 1),
        "blend_weight": float(weight),
    }


def _hitter_tendencies(model: SprayModel, bip: pd.DataFrame, sw: pd.DataFrame, stand: str) -> dict[str, Any]:
    s = _STAND_IDX[stand]
    own_all = np.zeros(VEC_LEN)
    np.add.at(own_all, bip["cell"].to_numpy(), bip["w"].to_numpy())
    ratio, n_all = _tendency_ratio(own_all, model.league_overall_cells[s])

    lg_bb = _norm(model.league_overall_bb[s])
    own_bb = np.bincount(bip["bb"].to_numpy(), weights=bip["w"].to_numpy(), minlength=len(BB_TYPES))
    bb_p = (own_bb + TENDENCY_K * lg_bb) / (own_bb.sum() + TENDENCY_K)
    bb_ratio = bb_p / lg_bb

    def _shift(col: str, lg_arr: np.ndarray) -> float:
        lg = lg_arr[s, ..., 0].sum() / max(lg_arr[s, ..., 1].sum(), 1e-9)
        ok = bip[col].notna()
        wsum = float(bip["w"][ok].sum())
        own = float((bip[col][ok] * bip["w"][ok]).sum())
        return ((own + TENDENCY_K * lg) / (wsum + TENDENCY_K)) - lg

    lg_sw = model.league_swing[s].sum(axis=(0, 1))
    own = sw[["n", "swing", "whiff", "foul", "in_play"]].sum().to_numpy(dtype=float)
    lg_rates = np.array([lg_sw[1] / lg_sw[0], lg_sw[2] / lg_sw[1], lg_sw[3] / lg_sw[1], lg_sw[4] / lg_sw[1]])
    dens = np.array([own[0], own[1], own[1], own[1]])
    nums = np.array([own[1], own[2], own[3], own[4]])
    own_rates = (nums + 4 * TENDENCY_K * lg_rates) / (dens + 4 * TENDENCY_K)
    return {
        "ratio": ratio,
        "n_all_bip": n_all,
        "bb_ratio": bb_ratio,
        "ev_shift": _shift("ev", model.league_ev),
        "xw_shift": _shift("xw", model.league_xw),
        "swing_ratio": own_rates / lg_rates,
        "overall_direction": _pull_center_oppo(own_all, stand) if n_all else None,
        "league_overall_direction": _pull_center_oppo(model.league_overall_cells[s], stand),
        "overall_gb": float(own_bb[0] / own_bb.sum()) if own_bb.sum() else None,
        "league_overall_gb": float(lg_bb[0]),
    }


def batter_profile(
    model: SprayModel,
    batter_id: int,
    *,
    stand: str,
    pitch_type: str,
    batter_name: str | None = None,
    zones: list[str] | None = None,
    include_balls: bool = True,
) -> dict[str, Any]:
    """All-zone (or selected-zone) pitch-to-field profile for one hitter × side × pitch type."""
    pt = _PITCH_TYPE_MAP.get(pitch_type.upper())
    if pt is None:
        raise ValueError(f"Unsupported pitch type {pitch_type}; choose from {SPRAY_PITCH_TYPES}")
    stand = stand.upper()
    bip, sw = _batter_frames(model, batter_id, stand)
    if bip.empty and sw.empty:
        raise ValueError(f"No {stand}-side pitches for batter {batter_id} in spray data")
    tend = _hitter_tendencies(model, bip, sw, stand)
    pt_i = _PT_IDX[pt]
    bip_pt = bip[bip["p"] == pt_i]
    sw_pt = sw[sw["p"] == pt_i]
    out_zones = {}
    for zid in zones or ZONE_IDS:
        z_i = _ZONE_IDX[zid]
        entry = _zone_entry(
            model,
            stand=stand,
            pt_i=pt_i,
            z_i=z_i,
            own_bip=bip_pt[bip_pt["z"] == z_i],
            own_sw=sw_pt[sw_pt["z"] == z_i],
            ratio=tend["ratio"],
            bb_ratio=tend["bb_ratio"],
            ev_shift=tend["ev_shift"],
            xw_shift=tend["xw_shift"],
            swing_ratio=tend["swing_ratio"],
        )
        entry["takeaway"] = spray_takeaway(entry, stand=stand, pitch_type=pt, batter_name=batter_name)
        out_zones[zid] = entry
    profile = {
        "batter_id": int(batter_id),
        "batter_name": batter_name or str(batter_id),
        "stand": stand,
        "pitch_type": pt,
        "pitch_name": PITCH_TYPE_NAMES[pt],
        "n_all_bip": len(bip),
        "n_all_bip_weighted": round(tend["n_all_bip"], 1),
        "n_pt_bip": len(bip_pt),
        "pt_counts": {
            SPRAY_PITCH_TYPES[int(k)]: int(v) for k, v in bip.groupby("p").size().items()
        },
        "overall_direction": tend["overall_direction"],
        "league_overall_direction": tend["league_overall_direction"],
        "overall_gb": tend["overall_gb"],
        "league_overall_gb": tend["league_overall_gb"],
        "zones": out_zones,
    }
    if include_balls:
        profile["balls"] = _balls_payload(bip_pt)
    return profile


def league_profile(model: SprayModel, *, stand: str, pitch_type: str) -> dict[str, Any]:
    pt = _PITCH_TYPE_MAP.get(pitch_type.upper())
    if pt is None:
        raise ValueError(f"Unsupported pitch type {pitch_type}; choose from {SPRAY_PITCH_TYPES}")
    stand = stand.upper()
    pt_i = _PT_IDX[pt]
    zones = {}
    for zid in ZONE_IDS:
        entry = _zone_entry(
            model, stand=stand, pt_i=pt_i, z_i=_ZONE_IDX[zid], own_bip=None, own_sw=None,
            ratio=None, bb_ratio=None, ev_shift=0.0, xw_shift=0.0, swing_ratio=None,
        )
        entry["takeaway"] = spray_takeaway(entry, stand=stand, pitch_type=pt, batter_name=None)
        zones[zid] = entry
    return {
        "batter_id": None,
        "batter_name": f"League average {stand}HH",
        "stand": stand,
        "pitch_type": pt,
        "pitch_name": PITCH_TYPE_NAMES[pt],
        "zones": zones,
        "balls": [],
    }


def _filter_sets(count: str, hand: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if count not in COUNT_FILTERS:
        raise ValueError(f"Unknown count filter {count!r}; choose from {list(COUNT_FILTERS)}")
    if hand not in HAND_FILTERS:
        raise ValueError(f"Unknown pitcher-hand filter {hand!r}; choose from {list(HAND_FILTERS)}")
    return COUNT_FILTERS[count], HAND_FILTERS[hand]


def league_filter_adjustment(
    model: SprayModel, *, stand: str, pt_i: int, count: str, hand: str
) -> dict[str, Any]:
    """How the league's spray / contact / swing profile shifts in a count / pitcher-hand slice.

    Ratios are (smoothed slice share) / (all-pitch share) for the same batter side and pitch
    type; the JS page mirrors this from the raw ``filter_tables`` in ``spray_meta``.
    """
    atoms, hands = _filter_sets(count, hand)
    s = _STAND_IDX[stand]
    sel = np.ix_(atoms, hands)
    k = FILTER_LEAGUE_K

    def split(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        a = arr[s, pt_i]
        return a.sum(axis=(0, 1)), a[sel].sum(axis=(0, 1))

    def share_ratio(all_v: np.ndarray, f_v: np.ndarray) -> np.ndarray:
        lg = _norm(all_v)
        p_f = (f_v + k * lg) / (f_v.sum() + k)
        return np.where(lg > 0, p_f / np.where(lg > 0, lg, 1.0), 1.0)

    def mean_shift(all_v: np.ndarray, f_v: np.ndarray) -> float:
        base = all_v[0] / all_v[1] if all_v[1] else 0.0
        return float((f_v[0] + k * base) / (f_v[1] + k) - base)

    ang_all, ang_f = split(model.lg_ang)
    bb_all, bb_f = split(model.lg_bb)
    ev_all, ev_f = split(model.lg_ev)
    xw_all, xw_f = split(model.lg_xw)
    sw_all, sw_f = split(model.lg_sw)

    def num(a: np.ndarray) -> np.ndarray:
        return np.array([a[1], a[2], a[3], a[4]])

    def den(a: np.ndarray) -> np.ndarray:
        return np.array([a[0], a[1], a[1], a[1]])

    r_all = num(sw_all) / np.maximum(den(sw_all), 1e-9)
    r_f = (num(sw_f) + k * r_all) / (den(sw_f) + k)
    return {
        "ang_ratio": share_ratio(ang_all, ang_f),
        "bb_ratio": share_ratio(bb_all, bb_f),
        "ev_shift": mean_shift(ev_all, ev_f),
        "xw_shift": mean_shift(xw_all, xw_f),
        "sw_ratio": np.where(r_all > 0, r_f / np.maximum(r_all, 1e-9), 1.0),
        "n_league_slice": float(ang_f.sum()),
    }


def _filtered_entry(
    model: SprayModel,
    e: dict[str, Any],
    *,
    stand: str,
    pitch_type: str,
    batter_name: str | None,
    own_bip: pd.DataFrame,
    own_sw: pd.DataFrame,
    adj: dict[str, Any],
) -> dict[str, Any]:
    """Shrink the hitter's slice toward his all-count profile × league slice adjustment."""
    s = _STAND_IDX[stand]
    cells = np.asarray(e["cells"], dtype=float)
    prior = _norm((cells.reshape(len(GROUPS), N_RING, N_ANG) * adj["ang_ratio"][:, None, :]).ravel())
    own_vec = np.zeros(VEC_LEN)
    own_bb = np.zeros(len(BB_TYPES))
    ev_sum = ev_n = xw_sum = xw_n = 0.0
    if not own_bip.empty:
        wv = own_bip["w"].to_numpy()
        np.add.at(own_vec, own_bip["cell"].to_numpy(), wv)
        np.add.at(own_bb, own_bip["bb"].to_numpy(), wv)
        ev_ok = own_bip["ev"].notna().to_numpy()
        xw_ok = own_bip["xw"].notna().to_numpy()
        ev_sum, ev_n = float((own_bip["ev"].to_numpy()[ev_ok] * wv[ev_ok]).sum()), float(wv[ev_ok].sum())
        xw_sum, xw_n = float((own_bip["xw"].to_numpy()[xw_ok] * wv[xw_ok]).sum()), float(wv[xw_ok].sum())
    n_own = float(own_vec.sum())
    post = (own_vec + SPRAY_K * prior) / (n_own + SPRAY_K)
    bb_base = np.array([e["bb"][t] for t in BB_TYPES])
    bb_prior = _norm(bb_base * adj["bb_ratio"])
    bb_post = (own_bb + SPRAY_K * bb_prior) / (own_bb.sum() + SPRAY_K)
    lg_bb = _norm(np.array([e["league_bb"][t] for t in BB_TYPES]) * adj["bb_ratio"])
    ev = (ev_sum + SPRAY_K * (e["ev"] + adj["ev_shift"])) / (ev_n + SPRAY_K)
    xw = (xw_sum + SPRAY_K * (e["xwoba_con"] + adj["xw_shift"])) / (xw_n + SPRAY_K)

    sw = e["swing"]
    r = adj["sw_ratio"]
    base = [min(sw["swing_rate"] * r[0], 0.99), min(sw["whiff_per_swing"] * r[1], 0.99),
            min(sw["foul_per_swing"] * r[2], 0.99), min(sw["in_play_per_swing"] * r[3], 0.99)]
    own = own_sw[["n", "swing", "whiff", "foul", "in_play"]].sum().to_numpy(dtype=float) if not own_sw.empty else np.zeros(5)
    swing = {
        "swing_rate": float((own[1] + SWING_K * base[0]) / (own[0] + SWING_K)),
        "whiff_per_swing": float((own[2] + SWING_K * base[1]) / (own[1] + SWING_K)),
        "foul_per_swing": float((own[3] + SWING_K * base[2]) / (own[1] + SWING_K)),
        "in_play_per_swing": float((own[4] + SWING_K * base[3]) / (own[1] + SWING_K)),
        "league_swing_rate": float(min(sw["league_swing_rate"] * r[0], 0.99)),
        "league_whiff_per_swing": float(min(sw["league_whiff_per_swing"] * r[1], 0.99)),
        "own_pitches": int(own_sw["cnt"].sum()) if not own_sw.empty else 0,
    }
    out = dict(e)
    out.update(
        cells=post,
        bb=dict(zip(BB_TYPES, bb_post.tolist(), strict=True)),
        league_bb=dict(zip(BB_TYPES, lg_bb.tolist(), strict=True)),
        ev=float(ev),
        league_ev=float(e["league_ev"] + adj["ev_shift"]),
        xwoba_con=float(xw),
        league_xwoba_con=float(e["league_xwoba_con"] + adj["xw_shift"]),
        hit_rate_from_spots=float(np.nansum(post * np.nan_to_num(model.cell_hit[s]))),
        landing_xwoba=float(np.nansum(post * np.nan_to_num(model.cell_xwoba[s]))),
        direction=_pull_center_oppo(post, stand),
        lanes_ground=_lanes(post, 0).tolist(),
        lanes_air=_lanes(post, 1).tolist(),
        swing=swing,
        n_own_bip=len(own_bip),
        n_own_weighted=round(n_own, 1),
        blend_weight=float(n_own / (n_own + SPRAY_K)) if batter_name else 0.0,
    )
    out["takeaway"] = spray_takeaway(out, stand=stand, pitch_type=pitch_type, batter_name=batter_name)
    return out


def filter_profile(
    model: SprayModel, profile: dict[str, Any], *, count: str = "all", hand: str = "all"
) -> dict[str, Any]:
    """Re-estimate a (full-precision) profile for a count group and/or pitcher hand.

    Same shrinkage as the base model, K = ``SPRAY_K``: the hitter's own balls in the slice are
    blended with a prior = his all-count profile for that pitch × zone, re-weighted by how the
    league's direction / contact mix shifts in that slice. Thin slices therefore lean on the
    prior (lower blend weight).
    """
    if count == "all" and hand == "all":
        return profile
    atoms, hands = _filter_sets(count, hand)
    stand = profile["stand"]
    pt = profile["pitch_type"]
    pt_i = _PT_IDX[pt]
    adj = league_filter_adjustment(model, stand=stand, pt_i=pt_i, count=count, hand=hand)
    bid = profile.get("batter_id")
    if bid is not None:
        bip, sw = _batter_frames(model, int(bid), stand)
        bip = bip[(bip["p"] == pt_i) & bip["k"].isin(atoms) & bip["ph"].isin(hands)]
        sw = sw[(sw["p"] == pt_i) & sw["k"].isin(atoms) & sw["ph"].isin(hands)]
    else:
        bip = model.bip.iloc[0:0]
        sw = model.swings.iloc[0:0]
    name = profile["batter_name"] if bid is not None else None
    zones = {}
    for zid, e in profile["zones"].items():
        z_i = _ZONE_IDX[zid]
        zones[zid] = _filtered_entry(
            model, e, stand=stand, pitch_type=pt, batter_name=name,
            own_bip=bip[bip["z"] == z_i], own_sw=sw[sw["z"] == z_i], adj=adj,
        )
    out = {**profile, "zones": zones}
    out["filter"] = {
        "count": count,
        "hand": hand,
        "label": f"{COUNT_FILTER_LABELS[count]}, {HAND_FILTER_LABELS[hand]}",
        "n_slice_bip": len(bip),
    }
    if "balls" in profile:
        out["balls"] = _balls_payload(bip) if bid is not None else []
    return out


_NAME_CACHE: dict[str, dict[int, str]] = {}


def _player_names(data_dir: Path | str) -> dict[int, str]:
    from pitch_dataset.situational import _chadwick_register

    key = str(Path(data_dir).resolve())
    if key not in _NAME_CACHE:
        reg = _chadwick_register(Path(data_dir)).dropna(subset=["key_mlbam"])
        _NAME_CACHE[key] = dict(
            zip(
                reg["key_mlbam"].astype(int),
                (reg["name_first"].fillna("").astype(str) + " " + reg["name_last"].fillna("").astype(str)).str.strip(),
                strict=True,
            )
        )
    return _NAME_CACHE[key]


DETAIL_BALL_FIELDS = [
    "d", "s", "pid", "pt", "z", "c", "x", "y", "bb", "ev", "la", "xw", "res", "k", "ph", "dist", "w",
]
DETAIL_SWING_FIELDS = ["s", "p", "z", "k", "ph", "n", "swing", "whiff", "foul", "in_play", "cnt"]


def _num(v: float, nd: int) -> float | None:
    return None if v is None or np.isnan(v) else round(float(v), nd)


def batter_detail(model: SprayModel, batter_id: int, data_dir: Path | str = "data") -> dict[str, Any]:
    """Everything the interactive page needs beyond per-pitch-type profiles, for one hitter.

    Balls in play (date order, with pitcher, pitch type, zone, count atom, pitcher hand, EV, LA,
    distance), weighted swing counts by pitch × zone × count atom × pitcher hand, and the share
    of pitches he saw under each Statcast fielding-alignment label.
    """
    names = _player_names(data_dir)
    b = model.bip[model.bip["batter"] == batter_id].sort_values(["date", "game_pk", "ab"])
    rows = []
    for r in b.itertuples(index=False):
        rows.append([
            r.date, "LR"[int(r.s)], int(r.pitcher), SPRAY_PITCH_TYPES[int(r.p)], ZONE_IDS[int(r.z)],
            int(r.cell), round(float(r.x_ft)), round(float(r.y_ft)), BB_SHORT[BB_TYPES[int(r.bb)]],
            _num(r.ev, 1), _num(r.la, 0), _num(r.xw, 3), r.events, int(r.k), "LR"[int(r.ph)],
            _num(r.dist, 0), round(float(r.w), 2),
        ])
    sw = model.swings[model.swings["batter"] == batter_id]
    sw_rows = [
        [int(r.s), int(r.p), int(r.z), int(r.k), int(r.ph), round(float(r.n), 2), round(float(r.swing), 2),
         round(float(r.whiff), 2), round(float(r.foul), 2), round(float(r.in_play), 2), int(r.cnt)]
        for r in sw.itertuples(index=False)
    ]
    align: dict[str, Any] = {}
    al = model.align[model.align["batter"] == batter_id] if model.align is not None else pd.DataFrame()
    for s_i, grp in al.groupby("s"):
        tot = float(grp["w"].sum())
        align["LR"[int(s_i)]] = {
            "if": {k: round(float(v) / tot, 3) for k, v in grp.groupby("if_al")["w"].sum().items()},
            "of": {k: round(float(v) / tot, 3) for k, v in grp.groupby("of_al")["w"].sum().items()},
        }
    pids = sorted({int(p) for p in b["pitcher"].unique()})
    return {
        "batter_id": int(batter_id),
        "balls": {"fields": DETAIL_BALL_FIELDS, "rows": rows},
        "swings": {"fields": DETAIL_SWING_FIELDS, "rows": sw_rows},
        "align": align,
        "pitchers": {str(p): names.get(p, str(p)) for p in pids},
    }


def pitcher_roster(
    model: SprayModel, data_dir: Path | str = "data", min_pitches: int = 100
) -> list[dict[str, Any]]:
    names = _player_names(data_dir)
    p = model.pitchers[model.pitchers["n"] >= min_pitches].sort_values("n", ascending=False)
    return [
        {"id": int(r.pitcher), "name": names.get(int(r.pitcher), str(r.pitcher)),
         "p_throws": r.p_throws, "n_pitches": int(r.n)}
        for r in p.itertuples(index=False)
    ]


def resolve_pitcher(
    model: SprayModel, pitcher: int | str, data_dir: Path | str = "data"
) -> tuple[int, str]:
    from pitch_dataset.situational import _select_player

    row = _select_player(model.pitch_mix[["pitcher"]], player=pitcher, player_name=None, id_col="pitcher")
    if row is None:
        raise ValueError(f"No pitcher matching {pitcher!r} in spray data")
    pid = int(row["pitcher"])
    return pid, _player_names(data_dir).get(pid, str(pid))


def pitcher_distribution(
    model: SprayModel, pitcher_id: int, data_dir: Path | str = "data"
) -> dict[str, Any]:
    """Season-weighted pitches by batter side × count atom × pitch type × zone for one pitcher."""
    mix = model.pitch_mix[model.pitch_mix["pitcher"] == pitcher_id]
    if mix.empty:
        raise ValueError(f"No pitches for pitcher {pitcher_id} in spray data")
    info = model.pitchers[model.pitchers["pitcher"] == pitcher_id].iloc[0]
    return {
        "id": int(pitcher_id),
        "name": _player_names(data_dir).get(int(pitcher_id), str(pitcher_id)),
        "p_throws": info["p_throws"],
        "n_pitches": int(info["n"]),
        "fields": ["s", "k", "p", "z", "w"],
        "rows": [
            [int(r.s), int(r.k), int(r.p), int(r.z), round(float(r.w), 1)]
            for r in mix.itertuples(index=False)
        ],
    }


def _balls_payload(bip: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for r in bip.itertuples(index=False):
        rows.append(
            {
                "z": ZONE_IDS[int(r.z)],
                "x": round(float(r.x_ft), 1),
                "y": round(float(r.y_ft), 1),
                "bb": BB_SHORT[BB_TYPES[int(r.bb)]],
                "ev": None if np.isnan(r.ev) else round(float(r.ev), 1),
                "la": None if np.isnan(r.la) else round(float(r.la)),
                "xw": None if np.isnan(r.xw) else round(float(r.xw), 3),
                "ev_name": r.events.replace("_", " "),
                "d": r.date,
            }
        )
    return rows


def _pct(v: float) -> str:
    return f"{100 * v:.0f}%"


def _side_word(lane_idx: int, stand: str) -> str:
    left = lane_idx < N_LANE // 2
    pull = left if stand == "R" else not left
    return "pull side" if pull else "opposite field"


def spray_takeaway(
    entry: dict[str, Any], *, stand: str, pitch_type: str, batter_name: str | None
) -> str:
    """One readable, data-backed sentence (plus a modest positioning hint when warranted)."""
    who = _short(batter_name) if batter_name else f"league {stand}HH"
    what = f"{entry['label'].lower()} {PITCH_TYPE_NAMES.get(pitch_type, pitch_type).lower()}s"
    gb = entry["bb"]["ground_ball"]
    lg_gb = entry["league_bb"]["ground_ball"]
    air = entry["bb"]["line_drive"] + entry["bb"]["fly_ball"]
    d = entry["direction"]
    lg_d = entry["league_direction"]
    parts = [f"{what[0].upper()}{what[1:]} vs {who}: {_pct(gb)} grounders"]
    if batter_name:
        parts[0] += f" (league {_pct(lg_gb)})"
    parts.append(f"{_pct(d['pull'])} pulled")
    if batter_name:
        parts[-1] += f" (league {_pct(lg_d['pull'])})"
    lanes = np.array(entry["lanes_ground"]) if gb >= 0.4 else np.array(entry["lanes_air"])
    lane_names = LANES_GROUND if gb >= 0.4 else LANES_AIR
    top = int(np.argmax(lanes))
    kind = "grounders" if gb >= 0.4 else "air balls"
    share = lanes[top] / max(lanes.sum(), 1e-9)
    parts.append(f"most common: {kind} {lane_names[top]} ({_pct(share)} of those)")
    xw = entry["xwoba_con"]
    lg_xw = entry["league_xwoba_con"]
    danger = f"xwOBA on contact {xw:.3f}"
    if batter_name:
        danger += f" vs league {lg_xw:.3f}"
    text = "; ".join(parts) + f". {danger}."
    if entry["n_league_bip"] < RARE_CELL_N:
        return (
            f"Rare contact: only {entry['n_league_bip']:.0f} league balls in play on "
            f"{what} — treat the map as noise. {text}"
        )
    if batter_name and entry["blend_weight"] < 0.25:
        text += " Mostly prior: few of his own balls in play here."
    elif batter_name:
        lg_lanes = np.array(entry["league_lanes_ground"] if gb >= 0.4 else entry["league_lanes_air"])
        lg_share = lg_lanes[top] / max(lg_lanes.sum(), 1e-9)
        if gb >= 0.45 and share - lg_share >= 0.05:
            text += (
                f" Grounders lean {_side_word(top, stand)} more than league — supports shading "
                "the infield that way (ball locations only; no fielder coordinates in this data)."
            )
        elif air >= 0.45 and d["pull"] - lg_d["pull"] >= 0.08:
            text += " Air contact is pull-heavy relative to league — outfield shift candidate."
    return text


def _short(name: str) -> str:
    if "," in name:
        return name.split(",")[0].strip()
    parts = name.split()
    if len(parts) > 1 and parts[-1].rstrip(".").lower() in {"jr", "sr", "ii", "iii"}:
        return parts[-2]
    return parts[-1] if parts else name


def resolve_batter(
    model: SprayModel, batter: int | str, data_dir: Path | str = "data"
) -> tuple[int, str]:
    """MLBAM id + display name via the shared situational name resolver."""
    from pitch_dataset.situational import _batter_display_name, _select_player

    frame = model.swings[["batter"]].drop_duplicates()
    row = _select_player(frame, player=batter, player_name=None, id_col="batter")
    if row is None:
        raise ValueError(f"No batter matching {batter!r} in spray data")
    bid = int(row["batter"])
    return bid, _batter_display_name(bid, data_dir)


def spray_roster(
    model: SprayModel, data_dir: Path | str = "data", min_side_pitches: float = 50.0
) -> list[dict[str, Any]]:
    """Every batter in the spray data: id, name, sides batted (most-used first), BIP count."""
    from pitch_dataset.situational import _chadwick_register

    reg = _chadwick_register(Path(data_dir)).dropna(subset=["key_mlbam"])
    names = dict(
        zip(
            reg["key_mlbam"].astype(int),
            reg["name_first"].fillna("").astype(str) + " " + reg["name_last"].fillna("").astype(str),
            strict=True,
        )
    )
    side_n = model.swings.groupby(["batter", "s"])["n"].sum().unstack(fill_value=0.0)
    bip_n = model.bip.groupby("batter").size()
    roster = []
    for bid, row in side_n.iterrows():
        sides = [
            ("L", "R")[int(s)]
            for s, n in sorted(row.items(), key=lambda kv: -kv[1])
            if n >= min_side_pitches
        ]
        if not sides:
            continue
        roster.append(
            {
                "id": int(bid),
                "name": names.get(int(bid), "").strip() or str(bid),
                "stands": sides,
                "n_bip": int(bip_n.get(bid, 0)),
                "_n": float(row.sum()),
            }
        )
    roster.sort(key=lambda r: -r.pop("_n"))
    return roster


def default_stand(model: SprayModel, batter_id: int) -> str:
    stands = batter_stands(model, batter_id)
    return max(stands, key=stands.get) if stands else "R"


# ---------------------------------------------------------------- serialization


CELL_SCALE = 1000
_BALL_FIELDS = ["z", "x", "y", "bb", "ev", "la", "xw", "ev_name", "d"]


def _compact_vec(vec: np.ndarray) -> list[int]:
    """Probabilities → integers per mille (keeps the static payload small)."""
    return np.rint(np.asarray(vec) * CELL_SCALE).astype(int).tolist()


def _compact_balls(balls: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for b in balls:
        row = [b[f] for f in _BALL_FIELDS]
        row[1], row[2] = round(b["x"]), round(b["y"])
        rows.append(row)
    return {"fields": _BALL_FIELDS, "rows": rows}


def compact_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe profile: cell vectors as ints per mille, balls as rows, rounded stats."""
    out = {k: v for k, v in profile.items() if k not in {"zones", "balls"}}
    out["cell_scale"] = CELL_SCALE
    out["balls"] = _compact_balls(profile.get("balls") or [])
    zones = {}
    for zid, e in profile["zones"].items():
        z = {}
        for k, v in e.items():
            if k == "league_cells":
                continue
            if k == "cells":
                z[k] = _compact_vec(v)
            elif isinstance(v, float):
                z[k] = None if np.isnan(v) else round(v, 4)
            elif isinstance(v, dict):
                z[k] = {
                    kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()
                }
            elif isinstance(v, list):
                z[k] = [round(x, 4) if isinstance(x, float) else x for x in v]
            else:
                z[k] = v
        zones[zid] = z
    out["zones"] = zones
    return out


def spray_meta(model: SprayModel) -> dict[str, Any]:
    s_names = ["L", "R"]
    return {
        "geometry": field_geometry(),
        "zones": [{"id": z["id"], "label": z["label"], "region": z["region"]} for z in LOCATION_ZONES],
        "pitch_types": [{"id": pt, "name": PITCH_TYPE_NAMES[pt]} for pt in SPRAY_PITCH_TYPES],
        "bb_types": [BB_SHORT[b] for b in BB_TYPES],
        "cell_xwoba": {
            s_names[i]: [None if np.isnan(v) else round(float(v), 3) for v in model.cell_xwoba[i]]
            for i in range(2)
        },
        "cell_hit": {
            s_names[i]: [None if np.isnan(v) else round(float(v), 3) for v in model.cell_hit[i]]
            for i in range(2)
        },
        "constants": {
            "spray_k": SPRAY_K,
            "tendency_k": TENDENCY_K,
            "swing_k": SWING_K,
            "season_weights": {str(k): v for k, v in SEASON_WEIGHTS.items()},
        },
        "seasons": model.seasons,
        "date_range": list(model.date_range),
        "n_bip": int(model.meta.get("n_bip", 0)),
        "n_pitches": int(model.meta.get("n_pitches", 0)),
        "filters": {
            "count": [{"id": k, "label": v, "atoms": list(COUNT_FILTERS[k])} for k, v in COUNT_FILTER_LABELS.items()],
            "hand": [{"id": k, "label": v, "hands": list(HAND_FILTERS[k])} for k, v in HAND_FILTER_LABELS.items()],
            "league_k": FILTER_LEAGUE_K,
        },
        # Raw league aggregates indexed [stand][pt][count atom][pitcher hand][...].
        "filter_tables": {
            name: np.round(arr, 1).tolist()
            for name, arr in (
                ("ang", model.lg_ang), ("bb", model.lg_bb), ("ev", model.lg_ev),
                ("xw", model.lg_xw), ("sw", model.lg_sw),
            )
        },
        "out_events": sorted(_OUT_EVENTS),
        "league_mix": _league_mix(model),
    }


def _league_mix(model: SprayModel) -> list:
    """Season-weighted pitches [stand][pitcher hand][count atom][pt][zone] (average-pitcher baseline)."""
    out = np.zeros((2, 2, N_ATOM, len(SPRAY_PITCH_TYPES), len(ZONE_IDS)))
    if model.pitch_mix is None or model.pitchers is None:
        return out.tolist()
    hand = model.pitchers.set_index("pitcher")["p_throws"].eq("R").astype(int)
    mix = model.pitch_mix
    ph = mix["pitcher"].map(hand).fillna(1).astype(int).to_numpy()
    np.add.at(out, (mix["s"].to_numpy(), ph, mix["k"].to_numpy(), mix["p"].to_numpy(), mix["z"].to_numpy()),
              mix["w"].to_numpy())
    return np.round(out).astype(int).tolist()


def format_field_text(profile: dict[str, Any], zone: str) -> str:
    e = profile["zones"][zone]
    bb = " / ".join(f"{BB_SHORT[t]} {_pct(e['bb'][t])}" for t in BB_TYPES)
    lg_bb = " / ".join(f"{BB_SHORT[t]} {_pct(e['league_bb'][t])}" for t in BB_TYPES)
    sw = e["swing"]
    lines = [
        f"{profile['batter_name']} ({profile['stand']}HH) · {profile['pitch_name']} · {e['label']}",
        f"  Contact mix: {bb}   (league {lg_bb})",
        (
            f"  Direction: pull {_pct(e['direction']['pull'])} / center "
            f"{_pct(e['direction']['center'])} / oppo {_pct(e['direction']['oppo'])}"
        ),
        (
            f"  Avg EV {e['ev']:.1f} mph (league {e['league_ev']:.1f}) · xwOBA on contact "
            f"{e['xwoba_con']:.3f} (league {e['league_xwoba_con']:.3f})"
        ),
        (
            f"  Swing {_pct(sw['swing_rate'])} · whiff/swing {_pct(sw['whiff_per_swing'])} · "
            f"foul/swing {_pct(sw['foul_per_swing'])}"
        ),
        (
            f"  Sample: {e['n_own_bip']} of his balls in play here (weighted "
            f"{e['n_own_weighted']}), blend weight {_pct(e['blend_weight'])} hitter-specific; "
            f"league cell n={e['n_league_bip']:.0f}"
        ),
        f"  Takeaway: {e['takeaway']}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- static demo page

_STATIC_DIR = Path(__file__).resolve().parent / "static" / "situational_web"


def build_demo_payload(
    model: SprayModel,
    *,
    hitters: list[str] | None = None,
    data_dir: Path | str = "data",
    min_side_pitches: float = 300.0,
    pitchers: list[str] | None = None,
) -> dict[str, Any]:
    hitters_out = []
    profiles: dict[str, Any] = {}
    details: dict[str, Any] = {}
    for name in hitters or DEMO_HITTERS:
        try:
            bid, display = resolve_batter(model, name, data_dir)
        except ValueError as exc:
            log.warning("Skipping demo hitter %s: %s", name, exc)
            continue
        stands = batter_stands(model, bid)
        sides = [s for s, n in sorted(stands.items(), key=lambda kv: -kv[1]) if n >= min_side_pitches]
        if not sides:
            continue
        hitters_out.append(
            {"id": bid, "name": display, "stands": sides, "n_bip": int((model.bip["batter"] == bid).sum())}
        )
        details[str(bid)] = batter_detail(model, bid, data_dir)
        for side in sides:
            for pt in SPRAY_PITCH_TYPES:
                prof = batter_profile(
                    model, bid, stand=side, pitch_type=pt, batter_name=display, include_balls=False
                )
                profiles[f"{bid}|{side}|{pt}"] = compact_profile(prof)
    league = {
        f"{side}|{pt}": compact_profile(league_profile(model, stand=side, pitch_type=pt))
        for side in ("L", "R")
        for pt in SPRAY_PITCH_TYPES
    }
    pitchers_out = []
    pitcher_dists: dict[str, Any] = {}
    for name in pitchers or DEMO_MATCHUP_PITCHERS:
        try:
            pid, _ = resolve_pitcher(model, name, data_dir)
            dist = pitcher_distribution(model, pid, data_dir)
        except ValueError as exc:
            log.warning("Skipping demo pitcher %s: %s", name, exc)
            continue
        pitchers_out.append(
            {"id": pid, "name": dist["name"], "p_throws": dist["p_throws"], "n_pitches": dist["n_pitches"]}
        )
        pitcher_dists[str(pid)] = dist
    return {
        "meta": spray_meta(model),
        "hitters": hitters_out,
        "profiles": profiles,
        "league": league,
        "details": details,
        "pitchers": pitchers_out,
        "pitcher_dists": pitcher_dists,
    }


PORTFOLIO_NAV = [
    ("index.html", "Situational pitch selection"),
    ("pitch-to-field.html", "Pitch-to-field"),
    ("zone-3d.html", "3D strike zone"),
]
LIVE_NAV = [
    ("/", "Situational pitch selection"),
    ("/field", "Pitch-to-field"),
    ("/zone3d", "3D strike zone"),
]


def render_field_page(
    payload: dict[str, Any] | None,
    *,
    nav: list[tuple[str, str]],
    active: str,
    banner: str = "",
) -> str:
    """Self-contained page; ``payload=None`` makes the JS use the live ``/api/field`` endpoints."""
    css = (_STATIC_DIR / "field.css").read_text(encoding="utf-8")
    js = "\n".join(
        (_STATIC_DIR / name).read_text(encoding="utf-8")
        for name in ("zone_map.js", "field_map.js", "field_defense.js", "field_modes.js")
    )
    nav_html = "".join(
        f'<a href="{href}"{" class=\"active\"" if href == active else ""}>{html.escape(label)}</a>'
        for href, label in nav
    )
    data_json = (
        json.dumps(payload, separators=(",", ":")).replace("</", "<\\/") if payload else "null"
    )
    return (
        _FIELD_PAGE_TEMPLATE.replace("{{CSS}}", css)
        .replace("{{NAV}}", nav_html)
        .replace("{{BANNER}}", f'<p class="portfolio-note">{banner}</p>' if banner else "")
        .replace("{{GENERATED}}", datetime.now().strftime("%Y-%m-%d"))
        .replace("{{BODY}}", (_STATIC_DIR / "field_body.html").read_text(encoding="utf-8"))
        .replace("{{DATA}}", data_json)
        .replace("{{JS}}", js)
    )


def write_field_html(payload: dict[str, Any], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = payload["meta"]
    banner = (
        f"Portfolio demo — {len(payload['hitters'])} hitters × 8 pitch types × 13 zones, "
        f"precomputed from {meta['n_bip']:,} MLB batted balls "
        f"({meta['date_range'][0]} → {meta['date_range'][1]}). The full roster with live lookups "
        "runs locally via <code>uv run pitch-dataset select-web</code> (<code>/field</code>). "
        '<a href="https://github.com/gdevers/pitch-dataset">Source on GitHub</a>.'
    )
    page = render_field_page(payload, nav=PORTFOLIO_NAV, active="pitch-to-field.html", banner=banner)
    path.write_text(page, encoding="utf-8")
    return path


_FIELD_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Pitch-to-Field · Where contact goes</title>
  <link rel="icon" href="data:," />
  <style>
{{CSS}}
  </style>
</head>
<body>
<main class="wide">
  <nav class="site-nav">{{NAV}}</nav>
  {{BANNER}}
{{BODY}}
  <p class="foot">Generated {{GENERATED}}.</p>
</main>
<script>window.P2F_STATIC = {{DATA}};</script>
<script>
{{JS}}
</script>
</body>
</html>
"""
