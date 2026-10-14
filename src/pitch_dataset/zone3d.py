"""3D strike zone: pitch trajectories through a true 3D zone volume, plus batted-ball arcs.

Coordinates are Statcast's: ``x`` is horizontal (+ toward the 1B side, the catcher's right),
``y`` is distance from the back tip of home plate toward the pitcher (rubber at 60.5 ft),
``z`` is height. All lengths are feet unless a name says ``_in``.

Trajectory reconstruction. Statcast publishes a 9-parameter constant-acceleration fit:
velocity ``(vx0, vy0, vz0)`` and acceleration ``(ax, ay, az)`` referenced at ``y = 50 ft``,
but not the position at ``y = 50``. With ``y(t) = 50 + vy0·t + ½·ay·t²`` we solve for the
release time ``t_r < 0`` where ``y(t_r) = release_pos_y``, pin the fit to the published release
point, back out ``(x0, z0)`` at ``y = 50`` and then evaluate the path anywhere. The crossing
is checked against Statcast's ``plate_x`` / ``plate_z`` (:func:`validate_reconstruction`).
Measured on 2026: the published ``plate_x/plate_z`` match the fitted path at
``y ≈ 8.5 in`` (mid-plate, where the plate's straight sides end) to ~0.05 in, and differ by
~1 in from the crossing of the *front* edge (``y = 17/12 ft``). The front-plane call test
below therefore uses the reconstructed front-edge crossing, not ``plate_x/plate_z``.

3D called-pitch test. The rule-book zone is the home-plate pentagon (17 in wide, 17 in deep)
extruded from ``sz_bot`` to ``sz_top`` (Statcast's per-pitch estimates). A pitch "touches" it
if the ball (radius 1.45 in) comes within one radius of the prism anywhere between the front
edge and the back tip, sampled every ~1 in of depth (exact point-to-prism distance). The 2D
comparison is the usual front-plane box: ``|x| ≤ 17/24 + r`` and ``sz_bot − r ≤ z ≤ sz_top + r``.

Tunneling. Each pitch type's mean position at a "decision point" plane 23.8 ft in front of
the plate (the commonly cited commit point, ~0.15–0.17 s before the plate) is compared with its
mean position at the front of the plate; the pair separations are reported in inches.

Batted balls. Landing / fielding spots come from ``hc_x`` / ``hc_y`` (see :mod:`spray`) scaled
to ``hit_distance_sc``; the 3D arc between contact and that spot is an approximate
drag-shortened parabola drawn client-side (shape only, not a flight model).
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pitch_dataset.location import assign_location_zones
from pitch_dataset.situational import _chadwick_register, _select_player
from pitch_dataset.spray import (
    _PITCH_TYPE_MAP,
    DEMO_HITTERS,
    LIVE_NAV,
    PORTFOLIO_NAV,
    SPRAY_PITCH_TYPES,
    hc_to_feet,
    spray_angle,
)
from pitch_dataset.storage import pitch_path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- geometry constants (ft)

FIT_Y = 50.0  # Statcast's v0 / a reference plane
RUBBER_Y = 60.5
PLATE_FRONT_Y = 17.0 / 12.0
PLATE_SIDE_Y = 8.5 / 12.0  # straight sides end here; angled edges run to the back tip at y = 0
PLATE_HALF_W = 17.0 / 24.0
BALL_RADIUS_FT = 1.45 / 12.0
DECISION_DIST_FT = 23.8  # in front of the plate's front edge
DECISION_Y = PLATE_FRONT_Y + DECISION_DIST_FT
CONTACT_Y = 1.4
N_DEPTH_SAMPLES = 18  # ~1 in apart across the 17 in plate depth
LEAGUE_SZ = (1.6, 3.4)

DEFAULT_SEASONS = (2026,)
DEFAULT_SAMPLE = 400
MAX_SAMPLE = 1500
DEMO_PER_PITCHER = 350
TUNNEL_MIN_N = 40
TUNNEL_MIN_SHARE = 0.05
TAKEAWAY_MIN_PLATE_SEP_IN = 6.0
N_BACK_ZONE_EXAMPLES = 8
EXAMPLE_MIN_MPH = 70.0  # keeps position players' lobs out of the highlighted examples
EXAMPLE_EXCLUDE_TYPES = ("EP", "PO", "KN")

DEMO_ZONE3D_PITCHERS = [
    "Dylan Cease", "Tarik Skubal", "Paul Skenes", "Kevin Gausman", "José Soriano",
    "Casey Mize", "Freddy Peralta", "Zack Wheeler", "Garrett Crochet", "Logan Webb",
]
DEFAULT_PITCHER = "Tarik Skubal"

PITCH_NAMES = {
    "FF": "4-seam fastball", "SI": "Sinker", "FC": "Cutter", "SL": "Slider", "ST": "Sweeper",
    "CU": "Curveball", "KC": "Knuckle curve", "SV": "Slurve", "CS": "Slow curve",
    "CH": "Changeup", "FS": "Splitter", "FO": "Forkball", "SC": "Screwball", "KN": "Knuckleball",
    "FA": "Fastball", "EP": "Eephus", "PO": "Pitchout",
}

# Called / swing outcome groups (``description``).
RESULT_GROUPS: dict[str, tuple[str, ...]] = {
    "CS": ("called_strike",),
    "B": ("ball", "blocked_ball", "pitchout", "intent_ball"),
    "SS": ("swinging_strike", "swinging_strike_blocked", "missed_bunt", "foul_tip", "swinging_pitchout"),
    "F": ("foul", "foul_bunt", "bunt_foul_tip"),
    "IP": ("hit_into_play",),
    "HBP": ("hit_by_pitch",),
}
RESULT_LABELS = {
    "CS": "Called strike", "B": "Ball", "SS": "Swinging strike", "F": "Foul",
    "IP": "In play", "HBP": "Hit by pitch", "O": "Other",
}
_DESC_TO_RESULT = {d: code for code, descs in RESULT_GROUPS.items() for d in descs}
COUNT_FILTERS = ("all", "ahead", "even", "behind", "two_strike")
_COUNT_RE = re.compile(r"^[0-3]-[0-2]$")

# 3D-vs-front-plane status for called pitches.
Z3_NA = 0  # not a called pitch
Z3_STRIKE_FRONT = 1  # called strike, passes the front-plane test
Z3_STRIKE_BACK_ONLY = 2  # called strike, misses the front plane but clips the zone behind it
Z3_STRIKE_MISS = 3  # called strike, misses the 3D zone entirely
Z3_BALL_TOUCH = 4  # called ball whose path touches the 3D zone
Z3_BALL = 5  # called ball, clean miss
Z3_LABELS = {
    Z3_NA: "Not a called pitch",
    Z3_STRIKE_FRONT: "Strike: crossed the front plane of the zone",
    Z3_STRIKE_BACK_ONLY: "Strike: missed the front plane, clipped the zone behind it",
    Z3_STRIKE_MISS: "Strike: never touched the 3D zone",
    Z3_BALL_TOUCH: "Ball: but the path touched the 3D zone",
    Z3_BALL: "Ball: missed the 3D zone",
}

_LOAD_COLS = [
    "pitcher", "batter", "player_name", "p_throws", "stand", "game_date", "game_pk",
    "at_bat_number", "pitch_number", "pitch_type", "release_speed", "release_spin_rate",
    "pfx_x", "pfx_z", "plate_x", "plate_z", "sz_top", "sz_bot", "release_pos_x",
    "release_pos_y", "release_pos_z", "vx0", "vy0", "vz0", "ax", "ay", "az", "description",
    "events", "bb_type", "balls", "strikes", "launch_speed", "launch_angle", "hit_distance_sc",
    "hc_x", "hc_y", "estimated_woba_using_speedangle",
]
_PHYSICS_COLS = [
    "release_pos_x", "release_pos_y", "release_pos_z", "vx0", "vy0", "vz0", "ax", "ay", "az",
    "plate_x", "plate_z",
]
_FLOAT32_COLS = [
    "release_speed", "release_spin_rate", "pfx_x", "pfx_z", "sz_top", "sz_bot",
    "launch_speed", "launch_angle", "hit_distance_sc", "estimated_woba_using_speedangle",
]

# Payload row layout: (key, source column, decimals or None for passthrough).
_ROW_FIELDS: list[tuple[str, str, int | None]] = [
    ("d", "game_date", None), ("b", "batter", None), ("st", "stand", None),
    ("bl", "balls", None), ("sk", "strikes", None), ("pt", "pitch_type", None),
    ("v", "release_speed", 1), ("sp", "release_spin_rate", 0), ("hb", "hb_in", 1),
    ("ivb", "ivb_in", 1), ("px", "plate_x", 2), ("pz", "plate_z", 2), ("fx", "front_x", 2),
    ("fz", "front_z", 2), ("top", "sz_top", 2), ("bot", "sz_bot", 2), ("x0", "x0", 3),
    ("z0", "z0", 3), ("vx", "vx0", 2), ("vy", "vy0", 2), ("vz", "vz0", 2), ("ax", "ax", 2),
    ("ay", "ay", 2), ("az", "az", 2), ("yr", "release_pos_y", 2), ("res", "res", None),
    ("desc", "description", None), ("evt", "events", None), ("f2", "front_hit", None),
    ("h3", "hit3d", None), ("z3", "z3", None), ("mf", "front_miss_in", 1),
    ("m3", "clear3d_in", 1), ("zid", "loc_zone", None), ("ppt", "p2f_pt", None),
    ("ls", "launch_speed", 1), ("la", "launch_angle", 0), ("dist", "bb_dist", 0),
    ("spr", "spray", 1), ("lx", "land_x", 1), ("ly", "land_y", 1), ("bb", "bb_type", None),
    ("xw", "estimated_woba_using_speedangle", 3), ("ex", "example", None),
]
ROW_KEYS = [k for k, _, _ in _ROW_FIELDS]

_STATIC_DIR = Path(__file__).resolve().parent / "static" / "zone3d"
_FIELD_CSS = Path(__file__).resolve().parent / "static" / "situational_web" / "field.css"


@dataclass
class Zone3DStore:
    """Per-pitch kinematics and 3D call tests for one or more seasons."""

    pitches: pd.DataFrame
    roster: list[dict[str, Any]]
    names: dict[int, str]
    rows_by_pitcher: dict[int, np.ndarray]
    seasons: tuple[int, ...]
    data_dir: Path
    n_dropped: int
    validation: dict[str, Any] = field(default_factory=dict)
    league_back_zone: dict[str, Any] = field(default_factory=dict)
    demo_batter_ids: list[int] = field(default_factory=list)
    _summary_cache: dict[int, dict[str, Any]] = field(default_factory=dict, repr=False)

    @property
    def date_range(self) -> tuple[str, str]:
        d = self.pitches["game_date"]
        return (str(d.min())[:10], str(d.max())[:10]) if len(d) else ("?", "?")


# ---------------------------------------------------------------- kinematics


def t_at_y(vy0: np.ndarray, ay: np.ndarray, y: float | np.ndarray) -> np.ndarray:
    """Time (s, relative to the y = 50 ft fit plane) when the fit reaches distance ``y``."""
    c = FIT_Y - np.asarray(y, dtype=float)
    disc = np.sqrt(np.maximum(vy0 * vy0 - 2.0 * ay * c, 0.0))
    flat = np.abs(ay) < 1e-6
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (-vy0 - disc) / np.where(flat, 1.0, ay)
    return np.where(flat, -c / vy0, t)


def _fit_origin(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """``(x0, z0)`` at y = 50 ft so that the fit passes through the published release point."""
    vy0, ay = df["vy0"].to_numpy(float), df["ay"].to_numpy(float)
    tr = t_at_y(vy0, ay, df["release_pos_y"].to_numpy(float))
    x0 = df["release_pos_x"].to_numpy(float) - df["vx0"].to_numpy(float) * tr - 0.5 * df["ax"].to_numpy(float) * tr**2
    z0 = df["release_pos_z"].to_numpy(float) - df["vz0"].to_numpy(float) * tr - 0.5 * df["az"].to_numpy(float) * tr**2
    return x0, z0


def _xz_at_y(
    x0: np.ndarray, z0: np.ndarray, df: pd.DataFrame, y: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t = t_at_y(df["vy0"].to_numpy(float), df["ay"].to_numpy(float), y)
    x = x0 + df["vx0"].to_numpy(float) * t + 0.5 * df["ax"].to_numpy(float) * t**2
    z = z0 + df["vz0"].to_numpy(float) * t + 0.5 * df["az"].to_numpy(float) * t**2
    return x, z, t


def zone_distance(
    x: np.ndarray, y: np.ndarray, z: np.ndarray, top: np.ndarray, bot: np.ndarray
) -> np.ndarray:
    """Distance (ft) from points with ``0 ≤ y ≤ 17/12`` to the plate-pentagon prism (0 inside)."""
    ax_ = np.abs(x)
    a, s = PLATE_HALF_W, PLATE_SIDE_Y  # a == s: the angled edges run at 45°
    over = ax_ - y * (a / s)
    beyond_corner = (ax_ + y) / (2.0 * s) > 1.0
    d_angled = np.where(
        beyond_corner, np.hypot(np.maximum(ax_ - a, 0.0), y - s), np.maximum(over, 0.0) / np.sqrt(2.0)
    )
    d_xy = np.where(y >= s, np.maximum(ax_ - a, 0.0), np.where(over > 0, d_angled, 0.0))
    d_z = np.maximum(np.maximum(bot - z, z - top), 0.0)
    return np.hypot(d_xy, d_z)


def front_plane_margin(x: np.ndarray, z: np.ndarray, top: np.ndarray, bot: np.ndarray) -> np.ndarray:
    """Box margin (ft) at the front plane: ≤ ball radius means the 2D test calls it a strike."""
    return np.maximum(np.maximum(np.abs(x) - PLATE_HALF_W, bot - z), z - top)


def _derive(df: pd.DataFrame) -> pd.DataFrame:
    """Add kinematics, 3D / 2D call tests, batted-ball geometry, and link keys."""
    x0, z0 = _fit_origin(df)
    fx, fz, t_front = _xz_at_y(x0, z0, df, PLATE_FRONT_Y)
    dpx, dpz, t_dp = _xz_at_y(x0, z0, df, DECISION_Y)
    top = df["sz_top"].to_numpy(float)
    bot = df["sz_bot"].to_numpy(float)
    top = np.where(np.isfinite(top), top, LEAGUE_SZ[1])
    bot = np.where(np.isfinite(bot), bot, LEAGUE_SZ[0])

    vy0, ay = df["vy0"].to_numpy(float), df["ay"].to_numpy(float)
    vx0, ax_ = df["vx0"].to_numpy(float), df["ax"].to_numpy(float)
    vz0, az = df["vz0"].to_numpy(float), df["az"].to_numpy(float)
    min_d = np.full(len(df), np.inf)
    for yk in np.linspace(PLATE_FRONT_Y, 0.0, N_DEPTH_SAMPLES):
        t = t_at_y(vy0, ay, yk)
        xk = x0 + vx0 * t + 0.5 * ax_ * t**2
        zk = z0 + vz0 * t + 0.5 * az * t**2
        min_d = np.minimum(min_d, zone_distance(xk, np.full_like(xk, yk), zk, top, bot))
    hit3d = min_d <= BALL_RADIUS_FT
    front_m = front_plane_margin(fx, fz, top, bot)
    front_hit = front_m <= BALL_RADIUS_FT

    res = df["description"].astype(object).map(_DESC_TO_RESULT).fillna("O").to_numpy(object)
    z3 = np.full(len(df), Z3_NA, dtype=np.int8)
    cs, ball = res == "CS", res == "B"
    z3[cs & front_hit] = Z3_STRIKE_FRONT
    z3[cs & ~front_hit & hit3d] = Z3_STRIKE_BACK_ONLY
    z3[cs & ~front_hit & ~hit3d] = Z3_STRIKE_MISS
    z3[ball & hit3d] = Z3_BALL_TOUCH
    z3[ball & ~hit3d] = Z3_BALL

    hx, hy = hc_to_feet(df["hc_x"], df["hc_y"])
    spray = spray_angle(hx, hy)
    dist = df["hit_distance_sc"].to_numpy(float)
    dist = np.where(np.isfinite(dist) & (dist > 0), dist, np.hypot(hx, hy))
    in_play = (res == "IP") & np.isfinite(spray) & np.isfinite(dist)
    spray = np.where(in_play, spray, np.nan)
    dist = np.where(in_play, dist, np.nan)
    rad = np.radians(spray)

    zones = assign_location_zones(df["plate_x"], df["plate_z"], df["stand"], df["sz_top"], df["sz_bot"])
    p2f = df["pitch_type"].astype(object).map(_PITCH_TYPE_MAP)

    f32 = np.float32
    return df.assign(
        x0=x0.astype(f32), z0=z0.astype(f32),
        front_x=fx.astype(f32), front_z=fz.astype(f32), t_front=t_front.astype(f32),
        dp_x=dpx.astype(f32), dp_z=dpz.astype(f32), t_dp=t_dp.astype(f32),
        sc_front_hit=front_plane_margin(df["plate_x"].to_numpy(float), df["plate_z"].to_numpy(float), top, bot)
        <= BALL_RADIUS_FT,
        front_hit=front_hit, hit3d=hit3d, z3=z3,
        front_miss_in=((front_m - BALL_RADIUS_FT) * 12.0).astype(f32),
        clear3d_in=((min_d - BALL_RADIUS_FT) * 12.0).astype(f32),
        res=pd.Categorical(res),
        hb_in=(df["pfx_x"].to_numpy(float) * 12.0).astype(f32),
        ivb_in=(df["pfx_z"].to_numpy(float) * 12.0).astype(f32),
        spray=spray.astype(f32), bb_dist=dist.astype(f32),
        land_x=(dist * np.sin(rad)).astype(f32), land_y=(dist * np.cos(rad)).astype(f32),
        loc_zone=pd.Categorical(zones["loc_zone"].to_numpy()),
        p2f_pt=pd.Categorical(p2f.to_numpy()),
    ).drop(columns=["hc_x", "hc_y"])


# ---------------------------------------------------------------- store


def _read_season(path: Path, columns: list[str]) -> pd.DataFrame:
    import pyarrow.parquet as pq

    have = set(pq.read_schema(path).names)
    return pd.read_parquet(path, columns=[c for c in columns if c in have])


def _display_name(last_first: Any) -> str:
    s = str(last_first or "")
    if ", " in s:
        last, first = s.split(", ", 1)
        return f"{first} {last}"
    return s


def build_zone3d_store(
    data_dir: Path | str = "data",
    seasons: Sequence[int] = DEFAULT_SEASONS,
    league: str = "mlb",
    pitches: pd.DataFrame | None = None,
) -> Zone3DStore:
    """Load (or reuse) pitches, keep only the needed columns, and precompute all 3D tests."""
    data_dir = Path(data_dir)
    if pitches is not None:
        frame = pitches[[c for c in _LOAD_COLS if c in pitches.columns]]
    else:
        frames = []
        for season in seasons:
            path = pitch_path(data_dir, season=season, league=league)
            if not path.exists():
                raise FileNotFoundError(
                    f"Missing {path}. Pull it first: `uv run pitch-dataset pull --season {season}`"
                )
            frames.append(_read_season(path, _LOAD_COLS))
        frame = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    missing = [c for c in _PHYSICS_COLS if c not in frame.columns]
    if missing:
        raise ValueError(f"Pitch frame lacks trajectory columns: {missing}")

    ok = frame[_PHYSICS_COLS].notna().all(axis=1) & (frame["vy0"] < 0)
    n_dropped = int((~ok).sum())
    frame = frame.loc[ok].reset_index(drop=True)
    frame = frame.assign(
        game_date=frame["game_date"].astype(str).str[:10],
        **{c: frame[c].astype("float32") for c in _FLOAT32_COLS if c in frame.columns},
        **{c: frame[c].astype("category") for c in ("player_name", "p_throws", "stand", "pitch_type",
                                                     "description", "events", "bb_type")
           if c in frame.columns},
    )
    for c in _LOAD_COLS:
        if c not in frame.columns:
            frame[c] = np.nan
    frame = _derive(frame)

    ids = set(frame["pitcher"].astype(int)) | set(frame["batter"].astype(int))
    names: dict[int, str] = {}
    try:
        reg = _chadwick_register(data_dir)
        reg = reg[reg["key_mlbam"].isin(ids)]
        names = {
            int(k): f"{f} {lname}"
            for k, f, lname in zip(reg["key_mlbam"], reg["name_first"], reg["name_last"], strict=True)
        }
    except FileNotFoundError:
        log.warning("No Chadwick register in %s; using Statcast pitcher names only.", data_dir)

    grouped = frame.groupby("pitcher", observed=True)
    roster = []
    for pid, g in grouped:
        pid = int(pid)
        if pid not in names:
            names[pid] = _display_name(g["player_name"].iloc[0])
        roster.append({
            "id": pid,
            "name": names[pid],
            "p_throws": str(g["p_throws"].mode().iloc[0]) if g["p_throws"].notna().any() else "R",
            "n_pitches": len(g),
        })
    roster.sort(key=lambda r: -r["n_pitches"])
    rows_by_pitcher = {int(k): np.asarray(v) for k, v in grouped.indices.items()}

    store = Zone3DStore(
        pitches=frame,
        roster=roster,
        names=names,
        rows_by_pitcher=rows_by_pitcher,
        seasons=tuple(int(s) for s in seasons),
        data_dir=data_dir,
        n_dropped=n_dropped,
    )
    store.validation = validate_reconstruction(store)
    store.league_back_zone = _back_zone_summary(store, frame, n_examples=6)
    for name in DEMO_HITTERS:
        row = _select_player(frame, player=name, player_name=None, id_col="batter")
        if row is not None:
            store.demo_batter_ids.append(int(row["batter"]))
    return store


def validate_reconstruction(store: Zone3DStore, n: int = 50000, seed: int = 0) -> dict[str, Any]:
    """Reconstructed plate crossing vs Statcast ``plate_x/plate_z`` (inches), several planes."""
    df = store.pitches
    if len(df) > n:
        df = df.sample(n, random_state=seed)
    x0, z0 = _fit_origin(df)
    px, pz = df["plate_x"].to_numpy(float), df["plate_z"].to_numpy(float)

    def stats(y: float, xo: np.ndarray = x0, zo: np.ndarray = z0, d: pd.DataFrame = df) -> dict[str, float]:
        x, z, _ = _xz_at_y(xo, zo, d, y)
        err = np.hypot(x - px, z - pz) * 12.0
        return {
            "y_ft": round(float(y), 4),
            "median_in": round(float(np.median(err)), 3),
            "p95_in": round(float(np.percentile(err, 95)), 3),
            "max_in": round(float(np.max(err)), 3),
            "bias_x_in": round(float(np.median(x - px) * 12.0), 3),
            "bias_z_in": round(float(np.median(z - pz) * 12.0), 3),
        }

    scan = np.round(np.arange(0.0, PLATE_FRONT_Y + 1e-9, 1.0 / 48.0), 4)
    meds = [stats(y)["median_in"] for y in scan]
    best_y = float(scan[int(np.argmin(meds))])
    shipped = df.assign(**{c: df[c].round(2) for c in ("vx0", "vy0", "vz0", "ax", "ay", "az", "release_pos_y")})
    return {
        "n": len(df),
        "front": stats(PLATE_FRONT_Y),
        "mid_plate": stats(PLATE_SIDE_Y),
        "best_fit": stats(best_y),
        "shipped_rounding_mid_plate": stats(
            PLATE_SIDE_Y, np.round(x0, 3), np.round(z0, 3), shipped
        ),
        "note": (
            "Statcast plate_x/plate_z agree with the fitted path at y≈8.5 in (mid-plate), "
            "not at the front edge (17 in)."
        ),
    }


# ---------------------------------------------------------------- name / filter helpers


def _fold(s: str) -> str:
    text = unicodedata.normalize("NFKD", str(s))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def resolve_pitcher(store: Zone3DStore, pitcher: int | str) -> int:
    """MLBAM id or name → pitcher id present in the store (``KeyError`` if unknown)."""
    try:
        pid = int(pitcher)
        if pid in store.rows_by_pitcher:
            return pid
    except (TypeError, ValueError):
        pass
    row = _select_player(store.pitches, player=pitcher, player_name=None, id_col="pitcher")
    if row is None:
        raise KeyError(f"Unknown pitcher: {pitcher}")
    return int(row["pitcher"])


def resolve_batter(store: Zone3DStore, batter: int | str, frame: pd.DataFrame | None = None) -> int:
    frame = store.pitches if frame is None else frame
    try:
        return int(batter)
    except (TypeError, ValueError):
        pass
    row = _select_player(frame, player=batter, player_name=None, id_col="batter")
    if row is None:
        raise KeyError(f"Unknown batter: {batter}")
    return int(row["batter"])


def _count_mask(df: pd.DataFrame, count: str | None) -> np.ndarray:
    if not count or count == "all":
        return np.ones(len(df), dtype=bool)
    b, s = df["balls"].to_numpy(float), df["strikes"].to_numpy(float)
    if count == "ahead":
        return s > b
    if count == "even":
        return s == b
    if count == "behind":
        return b > s
    if count == "two_strike":
        return s == 2
    if _COUNT_RE.match(count):
        cb, cs = (int(v) for v in count.split("-"))
        return (b == cb) & (s == cs)
    raise ValueError(f"count must be one of {COUNT_FILTERS} or 'B-S' like '3-2'")


def _result_mask(df: pd.DataFrame, result: str | None) -> np.ndarray:
    if not result or result == "all":
        return np.ones(len(df), dtype=bool)
    if result not in RESULT_LABELS:
        raise ValueError(f"result must be 'all' or one of {list(RESULT_LABELS)}")
    return (df["res"] == result).to_numpy()


def _pitcher_frame(store: Zone3DStore, pid: int) -> pd.DataFrame:
    return store.pitches.iloc[store.rows_by_pitcher[pid]]


# ---------------------------------------------------------------- summaries


def _r(v: Any, d: int = 1) -> float | None:
    return None if v is None or not np.isfinite(v) else round(float(v), d)


def _tunnel_stats(sub: pd.DataFrame) -> dict[str, Any]:
    """Per pitch type mean position at the decision plane vs the front of the plate."""
    n_all = len(sub)
    counts = sub["pitch_type"].value_counts()
    keep = [pt for pt, n in counts.items() if n >= max(TUNNEL_MIN_N, TUNNEL_MIN_SHARE * n_all)]
    types = []
    for pt in keep:
        g = sub[sub["pitch_type"] == pt]
        types.append({
            "pt": str(pt),
            "name": PITCH_NAMES.get(str(pt), str(pt)),
            "n": len(g),
            "share": round(len(g) / n_all, 3),
            "velo": _r(g["release_speed"].mean()),
            "hb_in": _r(g["hb_in"].mean()),
            "ivb_in": _r(g["ivb_in"].mean()),
            "dp": [_r(g["dp_x"].mean(), 3), _r(g["dp_z"].mean(), 3)],
            "plate": [_r(g["front_x"].mean(), 3), _r(g["front_z"].mean(), 3)],
            "release": [_r(g["release_pos_x"].mean(), 3), _r(g["release_pos_z"].mean(), 3)],
            "commit_ms": _r(1000 * (g["t_front"] - g["t_dp"]).mean(), 0),
            "coef": [
                _r(g[c].mean(), 3)
                for c in ("x0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az", "release_pos_y")
            ],
        })
    pairs = []
    for i, a in enumerate(types):
        for b in types[i + 1:]:
            dp = 12 * float(np.hypot(a["dp"][0] - b["dp"][0], a["dp"][1] - b["dp"][1]))
            pl = 12 * float(np.hypot(a["plate"][0] - b["plate"][0], a["plate"][1] - b["plate"][1]))
            rel = 12 * float(np.hypot(a["release"][0] - b["release"][0], a["release"][1] - b["release"][1]))
            pairs.append({
                "a": a["pt"], "b": b["pt"], "dp_in": round(dp, 1), "plate_in": round(pl, 1),
                "release_in": round(rel, 1), "ratio": round(pl / max(dp, 0.1), 2),
            })
    pairs.sort(key=lambda p: -p["ratio"])
    best = next((p for p in pairs if p["plate_in"] >= TAKEAWAY_MIN_PLATE_SEP_IN), None)
    commit = [t["commit_ms"] for t in types if t["commit_ms"] is not None]
    return {
        "n": n_all,
        "types": types,
        "pairs": pairs,
        "best": best,
        "commit_ms": round(float(np.mean(commit))) if commit else None,
    }


def _example_entry(store: Zone3DStore, row: pd.Series) -> dict[str, Any]:
    return {
        "row": int(row.name),
        "pitcher_id": int(row["pitcher"]),
        "pitcher": store.names.get(int(row["pitcher"]), str(row["pitcher"])),
        "batter_id": int(row["batter"]),
        "batter": store.names.get(int(row["batter"]), str(row["batter"])),
        "date": str(row["game_date"]),
        "pt": str(row["pitch_type"]),
        "count": f"{int(row['balls'])}-{int(row['strikes'])}",
        "z3": int(row["z3"]),
        "front_miss_in": _r(row["front_miss_in"]),
        "clear3d_in": _r(row["clear3d_in"]),
        "front_x": _r(row["front_x"], 2),
        "front_z": _r(row["front_z"], 2),
        "sz_top": _r(row["sz_top"], 2),
        "sz_bot": _r(row["sz_bot"], 2),
    }


def _back_zone_summary(store: Zone3DStore, sub: pd.DataFrame, n_examples: int = N_BACK_ZONE_EXAMPLES) -> dict[str, Any]:
    z3 = sub["z3"].to_numpy()
    res = sub["res"].to_numpy()
    cs, ball = res == "CS", res == "B"
    sc_hit = sub["sc_front_hit"].to_numpy()
    out = {
        "n_called_strikes": int(cs.sum()),
        "n_called_balls": int(ball.sum()),
        "strike_front": int((z3 == Z3_STRIKE_FRONT).sum()),
        "strike_back_only": int((z3 == Z3_STRIKE_BACK_ONLY).sum()),
        "strike_miss": int((z3 == Z3_STRIKE_MISS).sum()),
        "ball_touch": int((z3 == Z3_BALL_TOUCH).sum()),
        "ball_touch_front": int(((z3 == Z3_BALL_TOUCH) & sub["front_hit"].to_numpy()).sum()),
        "ball_touch_back_only": int(((z3 == Z3_BALL_TOUCH) & ~sub["front_hit"].to_numpy()).sum()),
        "statcast_plate_strike_miss": int((cs & ~sc_hit).sum()),
        "statcast_plate_ball_hit": int((ball & sc_hit).sum()),
    }
    real = (
        ~sub["pitch_type"].isin(EXAMPLE_EXCLUDE_TYPES).to_numpy()
        & (sub["release_speed"].to_numpy(float) >= EXAMPLE_MIN_MPH)
    )
    back = sub[real & (z3 == Z3_STRIKE_BACK_ONLY)].sort_values("front_miss_in", ascending=False)
    touch = sub[real & (z3 == Z3_BALL_TOUCH) & ~sub["front_hit"].to_numpy()].sort_values("clear3d_in")
    miss = sub[real & (z3 == Z3_STRIKE_MISS)].sort_values("clear3d_in", ascending=False)
    n_back = max(1, n_examples // 2)
    n_rest = max(1, (n_examples - n_back) // 2)
    picks = pd.concat([back.head(n_back), touch.head(n_rest), miss.head(n_rest)])
    out["examples"] = [_example_entry(store, r) for _, r in picks.iterrows()]
    return out


def _takeaways(name: str, tunnel: dict[str, Any], bz: dict[str, Any]) -> list[str]:
    last = name.split(" ")[-1] if name else "He"
    out = []
    best = tunnel.get("best")
    if best:
        out.append(
            f"{last}'s {best['a']} and {best['b']} are {best['dp_in']:.1f}\" apart at the decision point "
            f"(~{DECISION_DIST_FT:.0f} ft out) but {best['plate_in']:.1f}\" apart at the plate — "
            f"{best['ratio']:.1f}× more separation after the batter must commit."
        )
    if bz["n_called_strikes"]:
        share = bz["strike_back_only"] / bz["n_called_strikes"]
        out.append(
            f"{bz['strike_back_only']} of his {bz['n_called_strikes']:,} called strikes ({share:.1%}) "
            f"missed the front plane of the zone but clipped the 3D volume behind it; "
            f"{bz['strike_miss']} never touched it at all."
        )
    if bz["ball_touch"]:
        out.append(
            f"{bz['ball_touch']} pitches called balls had a path that touched the 3D zone "
            f"({bz['ball_touch_back_only']} only behind the front plane)."
        )
    return out


def _pitcher_summary(store: Zone3DStore, pid: int) -> dict[str, Any]:
    if pid not in store._summary_cache:
        sub = _pitcher_frame(store, pid)
        tunnel = _tunnel_stats(sub)
        bz = _back_zone_summary(store, sub)
        stand_mix = sub["stand"].value_counts().to_dict()
        store._summary_cache[pid] = {
            "tunnel": tunnel,
            "back_zone": bz,
            "takeaways": _takeaways(store.names.get(pid, ""), tunnel, bz),
            "zone": {
                "sz_top": _r(sub["sz_top"].mean(), 3),
                "sz_bot": _r(sub["sz_bot"].mean(), 3),
                "source": "average of his opponents' per-pitch Statcast sz_top / sz_bot",
            },
            "stand_mix": {str(k): int(v) for k, v in stand_mix.items()},
            "pitch_types": [
                {"pt": str(pt), "name": PITCH_NAMES.get(str(pt), str(pt)), "n": int(n)}
                for pt, n in sub["pitch_type"].value_counts().items() if n > 0
            ],
        }
    return store._summary_cache[pid]


# ---------------------------------------------------------------- public API


def zone3d_meta(store: Zone3DStore) -> dict[str, Any]:
    default = next((r for r in store.roster if r["name"] == DEFAULT_PITCHER), store.roster[0] if store.roster else None)
    return {
        "seasons": list(store.seasons),
        "date_range": list(store.date_range),
        "n_pitches": len(store.pitches),
        "n_dropped": store.n_dropped,
        "n_pitchers": len(store.roster),
        "default_pitcher_id": default["id"] if default else None,
        "validation": store.validation,
        "back_zone": store.league_back_zone,
        "geometry": {
            "fit_y": FIT_Y, "rubber_y": RUBBER_Y, "plate_front_y": round(PLATE_FRONT_Y, 4),
            "plate_side_y": round(PLATE_SIDE_Y, 4), "plate_half_w": round(PLATE_HALF_W, 4),
            "ball_r": round(BALL_RADIUS_FT, 4), "decision_y": round(DECISION_Y, 3),
            "decision_dist": DECISION_DIST_FT, "contact_y": CONTACT_Y, "league_sz": list(LEAGUE_SZ),
        },
        "pitch_names": PITCH_NAMES,
        "result_labels": RESULT_LABELS,
        "z3_labels": {str(k): v for k, v in Z3_LABELS.items()},
        "p2f_types": SPRAY_PITCH_TYPES,
        "demo_batter_ids": store.demo_batter_ids,
        "row_keys": ROW_KEYS,
    }


def zone3d_pitchers(store: Zone3DStore, q: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    roster = store.roster
    if q:
        needle = _fold(q.strip())
        roster = [r for r in roster if needle in _fold(r["name"]) or needle in str(r["id"])]
    return roster[:limit] if limit and limit > 0 else roster


def zone3d_batters(store: Zone3DStore, pitcher_id: int | str) -> list[dict[str, Any]]:
    pid = resolve_pitcher(store, pitcher_id)
    sub = _pitcher_frame(store, pid)
    g = sub.groupby("batter", observed=True).agg(
        n=("batter", "size"), stand=("stand", lambda s: s.mode().iloc[0] if len(s) else "R")
    ).sort_values("n", ascending=False)
    return [
        {"id": int(b), "name": store.names.get(int(b), str(b)), "stand": str(r["stand"]), "n": int(r["n"])}
        for b, r in g.iterrows()
    ]


def _stratified_sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Random sample that keeps in-play and called pitches represented (≈30% / 45%)."""
    if len(df) <= n:
        return df.sample(frac=1.0, random_state=seed)
    res = df["res"].to_numpy()
    groups = {"IP": res == "IP", "called": np.isin(res, ["CS", "B"]), "other": ~np.isin(res, ["IP", "CS", "B"])}
    quotas = {"IP": 0.30, "called": 0.45, "other": 0.25}
    picked = []
    for key, mask in groups.items():
        g = df[mask]
        picked.append(g.sample(min(len(g), round(quotas[key] * n)), random_state=seed))
    out = pd.concat(picked)
    if len(out) < n:
        rest = df.drop(index=out.index)
        out = pd.concat([out, rest.sample(min(len(rest), n - len(out)), random_state=seed)])
    return out.sample(frac=1.0, random_state=seed)


def _rows(df: pd.DataFrame) -> list[list[Any]]:
    cols = []
    for _key, col, dec in _ROW_FIELDS:
        s = df[col]
        if dec is not None:
            vals = pd.to_numeric(s, errors="coerce").astype(float).round(dec)
            vals = vals.astype(int) if dec == 0 and vals.notna().all() else vals
            out = [None if pd.isna(v) else (int(v) if dec == 0 else float(v)) for v in vals.tolist()]
        elif s.dtype == bool:
            out = [int(v) for v in s.tolist()]
        else:
            out = [None if pd.isna(v) else v for v in s.astype(object).tolist()]
            out = [int(v) if isinstance(v, (np.integer,)) else v for v in out]
        cols.append(out)
    return [list(r) for r in zip(*cols, strict=True)]


def zone3d_pitches(
    store: Zone3DStore,
    pitcher: int | str,
    batter: int | str | None = None,
    pitch_type: str | None = None,
    count: str | None = None,
    result: str | None = None,
    sample: int = DEFAULT_SAMPLE,
    seed: int = 0,
) -> dict[str, Any]:
    """One pitcher's payload: filtered sample of pitch rows + full-season tunnel / 3D-call stats."""
    pid = resolve_pitcher(store, pitcher)
    sub = _pitcher_frame(store, pid)
    summary = _pitcher_summary(store, pid)
    mask = _count_mask(sub, count) & _result_mask(sub, result)
    bid = None
    if batter not in (None, "", "all"):
        bid = resolve_batter(store, batter, sub)
        mask &= (sub["batter"] == bid).to_numpy()
    if pitch_type and pitch_type != "all":
        mask &= (sub["pitch_type"] == pitch_type).to_numpy()
    matched = sub[mask]
    sample = int(np.clip(sample, 1, MAX_SAMPLE))
    shown = _stratified_sample(matched, sample, seed)

    ex_rows = {e["row"]: (1 if e["z3"] == Z3_STRIKE_BACK_ONLY else 2 if e["z3"] == Z3_BALL_TOUCH else 3)
               for e in summary["back_zone"]["examples"]}
    ex_df = store.pitches.loc[[r for r in ex_rows if r not in shown.index]]
    shown = pd.concat([ex_df, shown])
    shown = shown.assign(example=[ex_rows.get(int(i), 0) for i in shown.index])
    shown = pd.concat([shown[shown["example"] > 0], shown[shown["example"] == 0]])

    meta = next(r for r in store.roster if r["id"] == pid)
    batter_ids = sorted(set(shown["batter"].astype(int)))
    return {
        "pitcher": {**meta},
        "filters": {
            "batter_id": bid, "pitch_type": pitch_type or "all", "count": count or "all",
            "result": result or "all", "sample": sample, "seed": seed,
        },
        "n_total": len(sub),
        "n_match": int(mask.sum()),
        "n_rows": len(shown),
        "n_examples": int((shown["example"] > 0).sum()),
        "keys": ROW_KEYS,
        "rows": _rows(shown),
        "row_ids": [int(i) for i in shown.index],
        "batters": {
            str(b): [store.names.get(b, str(b)), str(shown.loc[shown["batter"] == b, "stand"].iloc[0])]
            for b in batter_ids
        },
        **summary,
    }


def build_zone3d_demo_payload(
    store: Zone3DStore,
    pitchers: Sequence[str | int] | None = None,
    per_pitcher: int = DEMO_PER_PITCHER,
) -> dict[str, Any]:
    roster = []
    data: dict[str, Any] = {}
    for name in pitchers or DEMO_ZONE3D_PITCHERS:
        try:
            pid = resolve_pitcher(store, name)
        except KeyError:
            log.warning("Skipping demo pitcher %s: not in the pitch data", name)
            continue
        if str(pid) in data:
            continue
        data[str(pid)] = zone3d_pitches(store, pid, sample=per_pitcher)
        roster.append(data[str(pid)]["pitcher"])
    meta = zone3d_meta(store)
    if roster and meta["default_pitcher_id"] not in {r["id"] for r in roster}:
        meta["default_pitcher_id"] = roster[0]["id"]
    return {"meta": meta, "pitchers": roster, "data": data}


# ---------------------------------------------------------------- page


def render_zone3d_page(
    payload: dict[str, Any] | None,
    *,
    nav: list[tuple[str, str]],
    active: str,
    banner: str = "",
) -> str:
    """Self-contained page; ``payload=None`` makes the JS use the live ``/api/zone3d`` endpoints."""
    css = _FIELD_CSS.read_text(encoding="utf-8") + "\n" + (_STATIC_DIR / "zone3d.css").read_text(encoding="utf-8")
    vendor = "\n".join(
        (_STATIC_DIR / "vendor" / name).read_text(encoding="utf-8")
        for name in ("three.min.js", "OrbitControls.js")
    )
    nav_html = "".join(
        f'<a href="{href}"{" class=\"active\"" if href == active else ""}>{html.escape(label)}</a>'
        for href, label in nav
    )
    data_json = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/") if payload else "null"
    parts = {
        "CSS": css,
        "NAV": nav_html,
        "BANNER": f'<p class="portfolio-note">{banner}</p>' if banner else "",
        "GENERATED": datetime.now().strftime("%Y-%m-%d"),
        "BODY": (_STATIC_DIR / "zone3d_body.html").read_text(encoding="utf-8"),
        "DATA": data_json,
        "VENDOR": vendor,
        "JS": (_STATIC_DIR / "zone3d.js").read_text(encoding="utf-8"),
    }
    return re.sub(r"\{\{([A-Z]+)\}\}", lambda m: parts[m.group(1)], _ZONE3D_PAGE_TEMPLATE)


def write_zone3d_html(payload: dict[str, Any], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = payload["meta"]
    n_rows = sum(d["n_rows"] for d in payload["data"].values())
    n_full = sum(d["n_total"] for d in payload["data"].values())
    banner = (
        f"Portfolio demo — {len(payload['pitchers'])} pitchers, {n_rows:,} sampled pitches drawn in 3D "
        f"(tunneling and 3D-call stats use their full seasons, {n_full:,} pitches; MLB "
        f"{meta['date_range'][0]} → {meta['date_range'][1]}). Every pitcher, batter and filter runs "
        "live locally via <code>uv run pitch-dataset select-web</code> (<code>/zone3d</code>). "
        '<a href="https://github.com/gdevers/pitch-dataset">Source on GitHub</a>.'
    )
    page = render_zone3d_page(payload, nav=PORTFOLIO_NAV, active="zone-3d.html", banner=banner)
    path.write_text(page, encoding="utf-8")
    return path


_ZONE3D_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>3D strike zone · Pitch flight, tunnels &amp; back-of-zone calls</title>
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
  <p class="foot">Generated {{GENERATED}}. 3D rendering: three.js r147 (MIT).</p>
</main>
<script>window.Z3D_STATIC = {{DATA}};</script>
<script>
{{VENDOR}}
</script>
<script>
{{JS}}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- live routes


def register_zone3d_routes(
    app: Any,
    get_store: Callable[[], Zone3DStore | None],
    nav: list[tuple[str, str]] = LIVE_NAV,
) -> None:
    """Add ``/zone3d`` and ``/api/zone3d/*`` to a FastAPI app."""
    from fastapi import HTTPException, Query
    from fastapi.responses import HTMLResponse

    def need_store() -> Zone3DStore:
        store = get_store()
        if store is None:
            raise HTTPException(status_code=503, detail="3D strike zone unavailable: no pitch data loaded.")
        return store

    @app.get("/zone3d")
    def zone3d_page() -> HTMLResponse:
        return HTMLResponse(render_zone3d_page(None, nav=nav, active="/zone3d"))

    @app.get("/api/zone3d/meta")
    def api_zone3d_meta() -> dict[str, Any]:
        return zone3d_meta(need_store())

    @app.get("/api/zone3d/pitchers")
    def api_zone3d_pitchers(q: str | None = None, limit: int | None = Query(None, ge=1)) -> list[dict[str, Any]]:
        return zone3d_pitchers(need_store(), q=q, limit=limit)

    @app.get("/api/zone3d/batters")
    def api_zone3d_batters(pitcher_id: str) -> list[dict[str, Any]]:
        try:
            return zone3d_batters(need_store(), pitcher_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'\"")) from exc

    @app.get("/api/zone3d/pitches")
    def api_zone3d_pitches(
        pitcher_id: int | None = None,
        pitcher: str | None = None,
        batter_id: str | None = None,
        pitch_type: str | None = None,
        count: str | None = None,
        result: str | None = None,
        sample: int = Query(DEFAULT_SAMPLE, ge=1, le=MAX_SAMPLE),
        seed: int = 0,
    ) -> dict[str, Any]:
        store = need_store()
        who = pitcher_id if pitcher_id is not None else pitcher
        if who is None:
            raise HTTPException(status_code=400, detail="Pass pitcher_id or pitcher.")
        try:
            return zone3d_pitches(
                store, who, batter=batter_id, pitch_type=pitch_type, count=count,
                result=result, sample=sample, seed=seed,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'\"")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------- CLI (to be wired into cli.py)


def add_zone3d_parser(sub: argparse._SubParsersAction) -> None:
    z3 = sub.add_parser(
        "zone3d",
        help="3D strike zone: pitch paths, tunneling and 3D (back-of-zone) called-pitch checks",
    )
    z3.add_argument("--pitcher", type=str, default=None, help="Pitcher name or MLBAM id (text summary)")
    z3.add_argument("--seasons", type=str, default="2026", help="Comma-separated seasons (default: 2026)")
    z3.add_argument("--league", choices=("mlb", "minors"), default="mlb")
    z3.add_argument("--data-dir", type=str, default="data")
    z3.add_argument("--demo", action="store_true", help="Write the self-contained portfolio page")
    z3.add_argument(
        "--pitchers", type=str, default=None,
        help="Semicolon-separated pitcher names for --demo (default: built-in list)",
    )
    z3.add_argument("--per-pitcher", type=int, default=DEMO_PER_PITCHER, help="Sampled pitches per pitcher")
    z3.add_argument(
        "--html", type=str, default="docs/zone-3d.html",
        help="HTML output path for --demo (default: docs/zone-3d.html)",
    )
    z3.add_argument("--json", type=str, default=None, help="Optional JSON export of the payload")


def format_zone3d_text(payload: dict[str, Any]) -> str:
    p = payload["pitcher"]
    lines = [f"{p['name']} ({p['p_throws']}HP) · {payload['n_total']:,} pitches"]
    for t in payload["tunnel"]["types"]:
        lines.append(
            f"  {t['pt']:>2} {t['share']:6.1%}  {t['velo'] or 0:5.1f} mph  HB (catcher's +x) {t['hb_in'] or 0:+5.1f}\"  "
            f"IVB {t['ivb_in'] or 0:+5.1f}\""
        )
    lines.append("Tunnel pairs (decision point → plate, inches):")
    for pr in payload["tunnel"]["pairs"][:6]:
        lines.append(f"  {pr['a']}/{pr['b']}: {pr['dp_in']:5.1f} → {pr['plate_in']:5.1f}  ({pr['ratio']:.1f}×)")
    lines.extend(payload["takeaways"])
    return "\n".join(lines)


def cmd_zone3d(args: argparse.Namespace) -> int:
    seasons = [int(s) for s in args.seasons.split(",") if s.strip()]
    store = build_zone3d_store(args.data_dir, seasons=seasons, league=args.league)
    v = store.validation
    print(
        f"Reconstruction vs Statcast plate_x/z (n={v['n']:,}): mid-plate median {v['mid_plate']['median_in']}\" "
        f"p95 {v['mid_plate']['p95_in']}\"; front-edge median {v['front']['median_in']}\"",
        file=sys.stderr,
    )
    if args.demo:
        names = [s.strip() for s in args.pitchers.split(";")] if args.pitchers else None
        payload = build_zone3d_demo_payload(store, pitchers=names, per_pitcher=args.per_pitcher)
        out = write_zone3d_html(payload, args.html)
        who = ", ".join(p["name"] for p in payload["pitchers"])
        print(f"Wrote 3D strike zone page -> {out} ({out.stat().st_size / 1e6:.2f} MB; {who})", file=sys.stderr)
        if args.json:
            Path(args.json).write_text(json.dumps(payload), encoding="utf-8")
        return 0
    if not args.pitcher:
        raise SystemExit("--pitcher is required unless --demo is set.")
    try:
        payload = zone3d_pitches(store, args.pitcher, sample=50)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc
    print(format_zone3d_text(payload))
    if args.json:
        Path(args.json).write_text(json.dumps(payload), encoding="utf-8")
    return 0
