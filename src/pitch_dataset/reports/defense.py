"""Defensive alignment optimizer — numpy port of ``static/situational_web/field_defense.js``.

Same simplified reach model, 2023 shift-rule clamping, and greedy coordinate search as the
interactive pitch-to-field Defense mode, so the report's recommendation matches what a user
gets from "Optimize" in the browser. Coordinates are feet from home (x + toward RF, y toward CF).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

GB_SPEED, REACTION, IF_RUN, GLOVE, TRANSFER, THROW = 0.85, 0.3, 17.0, 4.0, 0.8, 110.0
RUNNER = {"R": 4.3, "L": 4.2}
MAX_IF_DEPTH, AIR_REACTION, OF_RUN, IF_AIR_RUN, BATTERY_RUN, DEFAULT_EV = 175.0, 0.5, 23.0, 20.0, 16.0, 85.0
HANG_DEFAULT = {"LD": 1.5, "FB": 4.2, "PU": 5.5}
FIRST_BASE = np.array([63.64, 63.64])
DIRT_CENTER = np.array([0.0, 60.5])
DIRT_RADIUS = 95.0

STANDARD_POLAR = {"1B": (112, 33), "2B": (150, 12), "SS": (148, -12), "3B": (116, -32),
                  "LF": (292, -27), "CF": (322, 0), "RF": (292, 27)}
FIELDERS = ["P", "C", "1B", "2B", "SS", "3B", "LF", "CF", "RF"]
MOVABLE = ["1B", "2B", "SS", "3B", "LF", "CF", "RF"]
INFIELD = ["1B", "2B", "SS", "3B"]
OUTFIELD = ["LF", "CF", "RF"]
BB_SHORT = {"ground_ball": "GB", "line_drive": "LD", "fly_ball": "FB", "popup": "PU"}


def _xy(r: float, a: float) -> np.ndarray:
    return np.array([r * math.sin(math.radians(a)), r * math.cos(math.radians(a))])


def _polar(p: np.ndarray) -> tuple[float, float]:
    return float(math.hypot(p[0], p[1])), float(math.degrees(math.atan2(p[0], p[1])))


def _wall(a: float) -> float:
    return 330.0 + 70.0 * math.cos(2 * math.radians(max(-45.0, min(45.0, a))))


def standard_positions() -> dict[str, np.ndarray]:
    pos = {"P": np.array([0.0, 60.5]), "C": np.array([0.0, -4.0])}
    for k, (r, a) in STANDARD_POLAR.items():
        pos[k] = _xy(r, a)
    return pos


def clamp(k: str, p: np.ndarray, rules: bool = True) -> np.ndarray:
    r, a = _polar(p)
    a = max(-46.0, min(46.0, a))
    if k in INFIELD:
        r = max(55.0, min(200.0 if rules else 230.0, r))
        x, y = _xy(r, a)
        if rules:
            right = k in ("1B", "2B")
            if right and x < 1:
                x = 1.0
            if not right and x > -1:
                x = -1.0
            d = math.hypot(x - DIRT_CENTER[0], y - DIRT_CENTER[1])
            if d > DIRT_RADIUS:
                x = DIRT_CENTER[0] + (x - DIRT_CENTER[0]) * DIRT_RADIUS / d
                y = DIRT_CENTER[1] + (y - DIRT_CENTER[1]) * DIRT_RADIUS / d
        dm = math.hypot(x - DIRT_CENTER[0], y - DIRT_CENTER[1])
        if dm < 18:
            ux, uy = (x - DIRT_CENTER[0]) / (dm or 1), (y - DIRT_CENTER[1]) / (dm or 1)
            x, y = DIRT_CENTER[0] + ux * 18, DIRT_CENTER[1] + uy * 18
        return np.array([x, y])
    r = max(170.0, min(_wall(a) - 6, r))
    return _xy(r, a)


def alignment_positions(if_label: str, of_label: str, stand: str) -> dict[str, np.ndarray]:
    pull = -1 if stand == "R" else 1
    pos = standard_positions()

    def rot(k: str, deg: float, dr: float = 0.0) -> None:
        r, a = _polar(pos[k])
        pos[k] = _xy(r + dr, a + pull * deg)

    if if_label == "Infield shade":
        for k in INFIELD:
            rot(k, 5)
    if if_label == "Strategic":
        rot("1B", 6)
        rot("3B", 7)
        rot("2B", 9, 10)
        rot("SS", 9, 10)
    if of_label == "Strategic":
        for k in OUTFIELD:
            rot(k, 8)
    for k in MOVABLE:
        pos[k] = clamp(k, pos[k], True)
    return pos


class BallSet:
    """Vectorized per-ball features (mirrors ``defenseFeatures``)."""

    def __init__(self, balls: pd.DataFrame, stand: str) -> None:
        bb = balls["bb_type"].map(BB_SHORT).fillna("FB").to_numpy()
        x, y = balls["x_ft"].to_numpy(float), balls["y_ft"].to_numpy(float)
        ang = np.degrees(np.arctan2(x, y))
        u = np.stack([np.sin(np.radians(ang)), np.cos(np.radians(ang))], axis=1)
        rec = np.hypot(x, y)
        ev = pd.to_numeric(balls["launch_speed"], errors="coerce").to_numpy(float)
        la = pd.to_numeric(balls["launch_angle"], errors="coerce").to_numpy(float)
        self.n = len(balls)
        self.gb = bb == "GB"
        self.u = u
        self.vg = np.maximum(25.0, np.where(np.isfinite(ev), ev, DEFAULT_EV) * 1.467 * GB_SPEED)
        self.stop = np.where(rec < 70, rec, np.inf)
        self.runner = RUNNER.get(stand, 4.3)
        self.hr = (balls["events"] == "home_run").to_numpy()
        dist = pd.to_numeric(balls["hit_distance_sc"], errors="coerce").to_numpy(float)
        d = np.where(np.isfinite(dist), dist, rec)
        wall = np.array([_wall(a) for a in ang])
        d = np.where(self.hr, d, np.minimum(d, wall - 3))
        self.land = u * d[:, None]
        hang = np.array([HANG_DEFAULT.get(b, 3.0) for b in bb])
        ok = np.isfinite(ev) & np.isfinite(la) & (la > 0)
        calc = np.maximum(0.4, 2 * np.nan_to_num(ev) * 1.467 * np.sin(np.radians(np.nan_to_num(la))) / 32.17)
        self.hang = np.where(ok, calc, hang)
        self.popup = bb == "PU"

    def can_field(self, k: str, p: np.ndarray) -> np.ndarray:
        out = np.zeros(self.n, dtype=bool)
        g = self.gb
        if g.any() and k not in OUTFIELD and k != "C":
            u = self.u[g]
            d = u @ p
            hi = np.minimum(np.minimum(self.stop[g], d + 35), MAX_IF_DEPTH)
            lo = np.maximum(4.0, np.minimum(d - 25, hi))
            steps = np.arange(0, 14)[None, :] * 5.0
            t = lo[:, None] + steps
            valid = t <= hi[:, None] + 0.01
            qx, qy = u[:, 0:1] * t, u[:, 1:2] * t
            tb = t / self.vg[g][:, None]
            tf = REACTION + np.maximum(0.0, np.hypot(qx - p[0], qy - p[1]) - GLOVE) / IF_RUN
            at_stop = np.abs(t - self.stop[g][:, None]) < 5.01
            feas = valid & ((tf <= tb) | at_stop)
            fld = np.maximum(tb, tf)
            to_first = np.hypot(qx - FIRST_BASE[0], qy - FIRST_BASE[1])
            total = fld + TRANSFER + to_first / THROW
            if k == "1B":
                total = np.minimum(total, fld + to_first / IF_RUN)
            out[g] = (feas & (total <= self.runner)).any(axis=1)
        a = ~g & ~self.hr
        if k == "C":
            a = a & self.popup
        if a.any():
            speed = OF_RUN if k in OUTFIELD else (BATTERY_RUN if k in ("P", "C") else IF_AIR_RUN)
            reach = GLOVE + np.maximum(0.0, self.hang[a] - AIR_REACTION) * speed
            dd = np.hypot(self.land[a, 0] - p[0], self.land[a, 1] - p[1])
            out[a] = dd <= reach
        return out


def evaluate(pos: dict[str, np.ndarray], balls: BallSet) -> float:
    covered = np.zeros(balls.n, dtype=bool)
    for k in FIELDERS:
        covered |= balls.can_field(k, pos[k])
    return float(covered.mean()) if balls.n else 0.0


def optimize(start: dict[str, np.ndarray], balls: BallSet, rules: bool = True) -> dict[str, np.ndarray]:
    pos = {k: v.copy() for k, v in start.items()}
    cols = {k: balls.can_field(k, pos[k]) for k in FIELDERS}
    cover = sum(cols[k].astype(int) for k in FIELDERS)
    step = {"IF": 12.0, "OF": 30.0}
    rounds = 0
    while rounds < 250 and step["IF"] >= 1.5:
        rounds += 1
        improved = False
        for k in MOVABLE:
            s = step["IF"] if k in INFIELD else step["OF"]
            best, best_gain = None, 1e-9
            for dx, dy in ((s, 0), (-s, 0), (0, s), (0, -s), (s, s), (s, -s), (-s, s), (-s, -s)):
                cand = clamp(k, pos[k] + np.array([dx, dy]), rules)
                if np.hypot(*(cand - pos[k])) < 0.5:
                    continue
                c = balls.can_field(k, cand)
                changed = c != cols[k]
                sole = (cover - cols[k].astype(int)) == 0
                m = changed & sole
                gain = float(c[m].sum() - (~c[m]).sum())
                if gain > best_gain:
                    best_gain, best = gain, (cand, c)
            if best is not None:
                cover = cover + best[1].astype(int) - cols[k].astype(int)
                cols[k] = best[1]
                pos[k] = best[0]
                improved = True
        if not improved:
            step["IF"] /= 2
            step["OF"] /= 2
    return pos


def recommend_alignment(bip: pd.DataFrame, stand: str) -> dict[str, Any] | None:
    """Best shift-legal alignment for one hitter's balls in play vs the standard alignment."""
    cols = ["x_ft", "y_ft", "bb_type", "launch_speed", "launch_angle", "hit_distance_sc", "events"]
    b = bip.dropna(subset=["x_ft", "y_ft", "bb_type"])[cols]
    b = b[b["bb_type"].isin(BB_SHORT)]
    if len(b) < 60:
        return None
    b = b.reset_index(drop=True)
    balls = BallSet(b, stand)
    std = standard_positions()
    std_rate = evaluate(std, balls)

    def fit(bs: BallSet) -> dict[str, np.ndarray]:
        best = None
        for start in (std, alignment_positions("Infield shade", "Standard", stand),
                      alignment_positions("Strategic", "Strategic", stand)):
            p2 = optimize(start, bs, True)
            r = evaluate(p2, bs)
            if best is None or r > best[1]:
                best = (p2, r)
        return best[0]

    opt = fit(balls)
    opt_rate = evaluate(opt, balls)
    # In-sample gains overstate the edge (positions are tuned to the same balls), so the headline is
    # 2-fold cross-validated: fit on one half of his balls in play, score on the other.
    fold = np.random.default_rng(0).permutation(len(b)) % 2
    cv = []
    for k in (0, 1):
        train, test = BallSet(b[fold != k].reset_index(drop=True), stand), BallSet(b[fold == k].reset_index(drop=True), stand)
        cv.append(evaluate(fit(train), test) - evaluate(std, test))
    cv_delta = float(np.mean(cv))
    pull = -1 if stand == "R" else 1
    moves = []
    for k in MOVABLE:
        r0, a0 = _polar(std[k])
        r1, a1 = _polar(opt[k])
        d = float(np.hypot(*(std[k] - opt[k])))
        if d > 6:
            moves.append({"pos": k, "dist": d, "pull_deg": (a1 - a0) * pull, "depth": r1 - r0})
    moves.sort(key=lambda m: -m["dist"])
    gb_pull = None
    gbs = b[b["bb_type"] == "ground_ball"]
    if len(gbs):
        ang = np.degrees(np.arctan2(gbs["x_ft"], gbs["y_ft"])) * pull
        gb_pull = float((ang > 15).mean())
    return {
        "n": len(b), "standard_rate": std_rate, "opt_rate": opt_rate,
        "delta_per100": 100 * cv_delta, "delta_in_sample": 100 * (opt_rate - std_rate), "moves": moves[:3],
        "standard": {k: tuple(map(float, std[k])) for k in MOVABLE},
        "optimized": {k: tuple(map(float, opt[k])) for k in MOVABLE},
        "gb_pull": gb_pull,
    }


def describe_moves(moves: list[dict[str, Any]]) -> str:
    parts = []
    for m in moves:
        txt = f"{m['pos']} {abs(m['pull_deg']):.0f}° toward {'pull' if m['pull_deg'] >= 0 else 'opposite'} side"
        if abs(m["depth"]) >= 5:
            txt += f", {abs(m['depth']):.0f} ft {'deeper' if m['depth'] > 0 else 'shallower'}"
        parts.append(txt)
    return "; ".join(parts)
