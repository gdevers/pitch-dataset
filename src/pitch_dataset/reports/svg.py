"""Inline-SVG chart primitives and color scales for print reports (no JS, no CDN).

Color system (stated in each report's legend):

* Accent ``#1d3f6e`` (navy) for structure and neutral data.
* Diverging scale for good/bad *from the report subject's perspective*: blue = poor,
  grey = average, red = good (Savant convention). Used for grades, percentiles and zone maps.
* Sequential navy ramp for frequency (where a pitcher throws; no good/bad meaning).
"""

from __future__ import annotations

import html
import math
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd

ACCENT = "#1d3f6e"
INK = "#1b1f24"
MUTED = "#6b7280"
GRID = "#e3e6ea"
FLAG = "#b7791f"

PITCH_COLORS = {
    "FF": "#d22d49", "FA": "#d22d49", "SI": "#e58a00", "FC": "#8a3b26", "SL": "#b8a400",
    "ST": "#c99a2e", "SV": "#7b8f00", "CU": "#0aa2bf", "KC": "#5b3cc4", "CS": "#0a7f96",
    "CH": "#1e9e3a", "FS": "#2b8c8c", "FO": "#2b8c8c", "SC": "#5a9e2b", "KN": "#555", "EP": "#999",
}
_LOW, _MID, _HIGH = (44, 93, 156), (238, 238, 236), (192, 57, 43)


def esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _hex(rgb: Sequence[float]) -> str:
    return "#" + "".join(f"{round(max(0, min(255, c))):02x}" for c in rgb)


def _lerp(a: Sequence[float], b: Sequence[float], t: float) -> list[float]:
    return [a[i] + (b[i] - a[i]) * t for i in range(3)]


def div_color(p: float | None) -> str:
    """0 → blue (poor), 0.5 → grey (average), 1 → red (good)."""
    if p is None or not np.isfinite(p):
        return "#f4f4f2"
    p = max(0.0, min(1.0, float(p)))
    return _hex(_lerp(_LOW, _MID, p / 0.5) if p < 0.5 else _lerp(_MID, _HIGH, (p - 0.5) / 0.5))


def grade_color(g: float | None) -> str:
    if g is None or not np.isfinite(g):
        return "#f4f4f2"
    return div_color((float(g) - 20.0) / 60.0)


def text_on(bg: str) -> str:
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    return "#fff" if (0.299 * r + 0.587 * g + 0.114 * b) < 150 else INK


def seq_color(t: float) -> str:
    t = max(0.0, min(1.0, float(t)))
    return _hex(_lerp((250, 251, 252), (29, 63, 110), t ** 0.8))


def pct(v: Any, d: int = 0) -> str:
    return "–" if v is None or not np.isfinite(v) else f"{100 * float(v):.{d}f}%"


def num(v: Any, d: int = 1) -> str:
    return "–" if v is None or not np.isfinite(v) else f"{float(v):.{d}f}"


def rate3(v: Any) -> str:
    """Baseball rate style: .312"""
    if v is None or not np.isfinite(v):
        return "–"
    s = f"{float(v):.3f}"
    return s.removeprefix("0")


def signed(v: Any, d: int = 1) -> str:
    return "–" if v is None or not np.isfinite(v) else f"{float(v):+.{d}f}"


def _svg(w: float, h: float, body: str, cls: str = "") -> str:
    return (f'<svg class="{cls}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" '
            f'width="{w:.0f}" height="{h:.0f}" font-family="inherit">{body}</svg>')


def _t(x: float, y: float, s: str, *, size: float = 8, anchor: str = "middle", fill: str = INK,
       weight: int = 400, extra: str = "") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" '
            f'font-weight="{weight}" {extra}>{esc(s)}</text>')


# ------------------------------------------------------------------ movement


def movement_plot(points: pd.DataFrame, means: pd.DataFrame, refs: dict[str, dict[str, Any]], *,
                  w: float = 300, h: float = 270, lim: float = 24.0) -> str:
    """HB (x) vs IVB (y), inches, catcher view. ``means`` rows: pitch_type, hb, ivb, label.

    ``refs``: pitch_type → league ``{"mean", "cov"}`` for the same family × hand (1-SD ellipse).
    """
    pad_l, pad_b, pad_t, pad_r = 26, 22, 6, 6
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b

    def sx(v: float) -> float:
        return pad_l + (v + lim) / (2 * lim) * pw

    def sy(v: float) -> float:
        return pad_t + (lim - v) / (2 * lim) * ph

    o = [f'<rect x="{pad_l}" y="{pad_t}" width="{pw}" height="{ph}" fill="#fff" stroke="{GRID}"/>']
    for v in range(-20, 21, 10):
        o.append(f'<line x1="{sx(v):.1f}" y1="{pad_t}" x2="{sx(v):.1f}" y2="{pad_t + ph}" stroke="{GRID}" stroke-width="{1.2 if v == 0 else 0.6}"/>')
        o.append(f'<line x1="{pad_l}" y1="{sy(v):.1f}" x2="{pad_l + pw}" y2="{sy(v):.1f}" stroke="{GRID}" stroke-width="{1.2 if v == 0 else 0.6}"/>')
        o.append(_t(sx(v), h - pad_b + 10, str(v), size=7, fill=MUTED))
        o.append(_t(pad_l - 4, sy(v) + 2.5, str(v), size=7, anchor="end", fill=MUTED))
    o.append(_t(pad_l + pw / 2, h - 2, "Horizontal break (in) · catcher view · 1B side →", size=7, fill=MUTED))
    o.append(_t(8, pad_t + ph / 2, "Induced vertical break (in)", size=7, fill=MUTED,
                extra=f'transform="rotate(-90 8 {pad_t + ph / 2:.1f})"'))
    for pt_code, ref in refs.items():
        mean, cov = np.asarray(ref["mean"]), np.asarray(ref["cov"])
        vals, vecs = np.linalg.eigh(cov)
        ang = math.degrees(math.atan2(vecs[1, 1], vecs[0, 1]))
        rx = math.sqrt(max(vals[1], 1e-6)) * pw / (2 * lim)
        ry = math.sqrt(max(vals[0], 1e-6)) * ph / (2 * lim)
        c = PITCH_COLORS.get(pt_code, MUTED)
        o.append(f'<ellipse cx="{sx(mean[0]):.1f}" cy="{sy(mean[1]):.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
                 f'transform="rotate({-ang:.1f} {sx(mean[0]):.1f} {sy(mean[1]):.1f})" fill="{c}" fill-opacity="0.07" '
                 f'stroke="{c}" stroke-opacity="0.55" stroke-dasharray="3 2" stroke-width="0.8"/>')
    for row in points.itertuples():
        if not (np.isfinite(row.hb) and np.isfinite(row.ivb)):
            continue
        c = PITCH_COLORS.get(row.pitch_type, MUTED)
        o.append(f'<circle cx="{sx(max(-lim, min(lim, row.hb))):.1f}" cy="{sy(max(-lim, min(lim, row.ivb))):.1f}" r="1.3" fill="{c}" fill-opacity="0.35"/>')
    for row in means.itertuples():
        c = PITCH_COLORS.get(row.pitch_type, MUTED)
        x, y = sx(row.hb), sy(row.ivb)
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{c}" stroke="#fff" stroke-width="1.4"/>')
        o.append(_t(x + 8, y + 3, row.pitch_type, size=8, anchor="start", weight=700, fill=c,
                    extra='paint-order="stroke" stroke="#fff" stroke-width="2.5"'))
    return _svg(w, h, "".join(o), "chart")


# ------------------------------------------------------------------ location heat map


def location_heatmap(px: np.ndarray, pz: np.ndarray, *, sz_top: float = 3.4, sz_bot: float = 1.6,
                     w: float = 92, h: float = 104, title: str = "", sub: str = "") -> str:
    """Smoothed pitch-location density, catcher view, rule-book box overlaid."""
    from scipy.ndimage import gaussian_filter

    x0, x1, z0, z1 = -2.0, 2.0, 0.4, 4.6
    nb_x, nb_z = 24, 25
    top_pad = 13 if title else 2
    pw, ph = w - 4, h - top_pad - (9 if sub else 2)
    ok = np.isfinite(px) & np.isfinite(pz)
    hist, _, _ = np.histogram2d(px[ok], pz[ok], bins=[nb_x, nb_z], range=[[x0, x1], [z0, z1]])
    dens = gaussian_filter(hist, sigma=1.6)
    mx = dens.max() if dens.size and dens.max() > 0 else 1.0
    cw, ch = pw / nb_x, ph / nb_z
    o = []
    if title:
        o.append(_t(w / 2, 9, title, size=7.5, weight=700))
    for i in range(nb_x):
        for j in range(nb_z):
            t = dens[i, j] / mx
            if t < 0.06:
                continue
            o.append(f'<rect x="{2 + i * cw:.2f}" y="{top_pad + (nb_z - 1 - j) * ch:.2f}" width="{cw + 0.3:.2f}" '
                     f'height="{ch + 0.3:.2f}" fill="{seq_color(t)}"/>')

    def sx(v: float) -> float:
        return 2 + (v - x0) / (x1 - x0) * pw

    def sz(v: float) -> float:
        return top_pad + (z1 - v) / (z1 - z0) * ph

    o.append(f'<rect x="2" y="{top_pad}" width="{pw}" height="{ph}" fill="none" stroke="{GRID}"/>')
    hw = 0.708
    o.append(f'<rect x="{sx(-hw):.1f}" y="{sz(sz_top):.1f}" width="{sx(hw) - sx(-hw):.1f}" height="{sz(sz_bot) - sz(sz_top):.1f}" '
             f'fill="none" stroke="{INK}" stroke-width="0.9"/>')
    for k in (1, 2):
        xv = -hw + k * 2 * hw / 3
        zv = sz_bot + k * (sz_top - sz_bot) / 3
        o.append(f'<line x1="{sx(xv):.1f}" y1="{sz(sz_top):.1f}" x2="{sx(xv):.1f}" y2="{sz(sz_bot):.1f}" stroke="{INK}" stroke-opacity="0.25" stroke-width="0.5"/>')
        o.append(f'<line x1="{sx(-hw):.1f}" y1="{sz(zv):.1f}" x2="{sx(hw):.1f}" y2="{sz(zv):.1f}" stroke="{INK}" stroke-opacity="0.25" stroke-width="0.5"/>')
    if sub:
        o.append(_t(w / 2, h - 1.5, sub, size=6.5, fill=MUTED))
    return _svg(w, h, "".join(o), "heat")


# ------------------------------------------------------------------ 13-zone grid


def zone_grid(values: dict[str, float], ns: dict[str, float], *, stand: str, color: Callable[[str, float], str],
              fmt: Callable[[float], str], min_n: float = 12, cell: float = 15.0, title: str = "") -> str:
    """Statcast-style 13-zone chart in catcher view from batter-relative zone ids (location.py).

    ``color(zone_id, value)`` returns the fill, so cells can be colored against a per-zone reference.
    """
    top_pad = 11 if title else 1
    W = 5 * cell
    o = []
    if title:
        o.append(_t(W / 2 + 1, 8, title, size=7, weight=700))
    flip = stand == "L"  # RHH: "in" is the catcher's left; LHH: catcher's right

    def col_x(side: str) -> float:  # side in {"in", "mid", "away"}
        idx = {"in": 0, "mid": 1, "away": 2}[side]
        if flip:
            idx = 2 - idx
        return 1 + cell + idx * cell

    def cell_fill(zid: str) -> tuple[str, str, bool]:
        v, n = values.get(zid), ns.get(zid, 0)
        small = n < min_n
        if v is None or not np.isfinite(v):
            return "#f4f4f2", "", True
        return ("#f4f4f2" if small else color(zid, v)), fmt(v), small

    for row, zrow in (("up", 0), ("down", 1)):
        for side in ("in", "away"):
            zid = f"chase_{row}_{side}"
            fill, label, small = cell_fill(zid)
            left = (side == "in") != flip
            x = 1 if left else 1 + 2.5 * cell
            y = top_pad + zrow * 2.5 * cell
            o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{2.5 * cell:.1f}" height="{2.5 * cell:.1f}" fill="{fill}" stroke="#fff" stroke-width="1"/>')
            tx = x + (0.55 * cell if left else 2.5 * cell - 0.55 * cell)
            ty = y + (0.62 * cell if zrow == 0 else 2.5 * cell - 0.3 * cell)
            o.append(_t(tx, ty, label, size=6.2, fill=MUTED if small else text_on(fill)))
    inner = [["up_in", "up_mid", "up_away"], ["mid_in", "heart", "mid_away"], ["down_in", "down_mid", "down_away"]]
    for r, row_ids in enumerate(inner):
        for zid in row_ids:
            side = "in" if zid.endswith("_in") else ("away" if zid.endswith("_away") else "mid")
            fill, label, small = cell_fill(zid)
            x, y = col_x(side), top_pad + cell + r * cell
            o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" fill="{fill}" stroke="#fff" stroke-width="1"/>')
            o.append(_t(x + cell / 2, y + cell / 2 + 2.2, label, size=6.2, fill=MUTED if small else text_on(fill)))
    o.append(f'<rect x="{1 + cell:.1f}" y="{top_pad + cell:.1f}" width="{3 * cell:.1f}" height="{3 * cell:.1f}" fill="none" stroke="{INK}" stroke-width="1"/>')
    return _svg(W + 2, top_pad + 5 * cell + 1, "".join(o), "zone")


# ------------------------------------------------------------------ trends


def trend_chart(dates: Sequence[pd.Timestamp], values: Sequence[float], *, w: float = 230, h: float = 78,
                rolling: int = 3, fmt: str = "{:.1f}", stints: Sequence[dict[str, Any]] = (),
                baseline: float | None = None, color: str = ACCENT, flag_from: pd.Timestamp | None = None,
                date_range: tuple[pd.Timestamp, pd.Timestamp] | None = None) -> str:
    """Per-game points, rolling mean line, optional baseline, IL shading, and flagged window."""
    d = pd.to_datetime(pd.Series(list(dates)))
    v = pd.Series(list(values), dtype=float)
    ok = v.notna() & d.notna()
    d, v = d[ok].reset_index(drop=True), v[ok].reset_index(drop=True)
    pad_l, pad_r, pad_t, pad_b = 30, 6, 4, 13
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
    if len(v) == 0:
        return _svg(w, h, _t(w / 2, h / 2, "no data", size=8, fill=MUTED))
    lo_d, hi_d = date_range if date_range else (d.min(), d.max())
    span = max((hi_d - lo_d).days, 1)
    vmin, vmax = float(v.min()), float(v.max())
    if baseline is not None:
        vmin, vmax = min(vmin, baseline), max(vmax, baseline)
    padv = max((vmax - vmin) * 0.12, 1e-6)
    vmin, vmax = vmin - padv, vmax + padv

    def sx(t: pd.Timestamp) -> float:
        return pad_l + (t - lo_d).days / span * pw

    def sy(val: float) -> float:
        return pad_t + (vmax - val) / (vmax - vmin) * ph

    o = [f'<rect x="{pad_l}" y="{pad_t}" width="{pw}" height="{ph}" fill="#fff" stroke="{GRID}"/>']
    for s in stints:
        a = max(pd.Timestamp(s["start"]), lo_d)
        b = min(pd.Timestamp(s["end"]) if s.get("end") is not None else hi_d, hi_d)
        if b <= a:
            continue
        o.append(f'<rect x="{sx(a):.1f}" y="{pad_t}" width="{max(sx(b) - sx(a), 1.5):.1f}" height="{ph}" fill="#9aa3ad" fill-opacity="0.22"/>')
        o.append(_t(sx(a) + 2, pad_t + 8, "IL", size=6.5, anchor="start", fill=MUTED, weight=700))
    if flag_from is not None:
        o.append(f'<rect x="{sx(flag_from):.1f}" y="{pad_t}" width="{sx(hi_d) - sx(flag_from):.1f}" height="{ph}" fill="{FLAG}" fill-opacity="0.10"/>')
    for k in range(3):
        val = vmin + padv + k * (vmax - vmin - 2 * padv) / 2
        o.append(f'<line x1="{pad_l}" y1="{sy(val):.1f}" x2="{pad_l + pw}" y2="{sy(val):.1f}" stroke="{GRID}" stroke-width="0.5"/>')
        o.append(_t(pad_l - 3, sy(val) + 2.5, fmt.format(val), size=6.5, anchor="end", fill=MUTED))
    if baseline is not None:
        o.append(f'<line x1="{pad_l}" y1="{sy(baseline):.1f}" x2="{pad_l + pw}" y2="{sy(baseline):.1f}" stroke="{MUTED}" stroke-dasharray="3 2" stroke-width="0.8"/>')
    for t, val in zip(d, v, strict=True):
        o.append(f'<circle cx="{sx(t):.1f}" cy="{sy(val):.1f}" r="1.5" fill="{color}" fill-opacity="0.35"/>')
    roll = v.rolling(rolling, min_periods=1).mean()
    pts = " ".join(f"{sx(t):.1f},{sy(val):.1f}" for t, val in zip(d, roll, strict=True))
    o.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.4"/>')
    for m in pd.date_range(lo_d.normalize(), hi_d, freq="MS"):
        if m < lo_d:
            continue
        o.append(_t(sx(m), h - 3, m.strftime("%b"), size=6.5, fill=MUTED))
    return _svg(w, h, "".join(o), "trend")


# ------------------------------------------------------------------ spray / defense


def _wall(angle_deg: float) -> float:
    a = math.radians(max(-45.0, min(45.0, angle_deg)))
    return 330.0 + 70.0 * math.cos(2 * a)


def spray_field(balls: pd.DataFrame, *, standard: dict[str, tuple[float, float]] | None = None,
                optimized: dict[str, tuple[float, float]] | None = None, w: float = 270, h: float = 236,
                color_col: str = "result") -> str:
    """Batted balls (x_ft, y_ft) on a generic park plus standard (hollow) / optimized (solid) fielders."""
    scale = min(w / 640.0, (h - 8) / 420.0)
    cx, cy = w / 2, h - 6

    def p(x: float, y: float) -> tuple[float, float]:
        return cx + x * scale, cy - y * scale

    o = []
    wall = [p(_wall(a) * math.sin(math.radians(a)), _wall(a) * math.cos(math.radians(a))) for a in np.arange(-45, 45.1, 3)]
    fair = [p(0, 0)] + wall
    o.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in fair) + '" fill="#f3f6f1" stroke="#c9d2c4" stroke-width="0.8"/>')
    infield = [p(0, 0), p(63.6, 63.6), p(0, 127.3), p(-63.6, 63.6)]
    o.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in infield) + '" fill="none" stroke="#c9d2c4" stroke-width="0.8"/>')
    arc = [p(155 * math.sin(math.radians(a)), 155 * math.cos(math.radians(a))) for a in np.arange(-45, 45.1, 3)]
    o.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in arc) + '" fill="none" stroke="#d9cbb3" stroke-width="0.8"/>')
    colors = {"out": "#9a9a94", "hit": "#d7301f", "hr": "#7f0000"}
    for b in balls.itertuples():
        if not (np.isfinite(b.x_ft) and np.isfinite(b.y_ft)):
            continue
        x, y = p(b.x_ft, b.y_ft)
        c = colors.get(getattr(b, color_col), "#9a9a94")
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" fill="{c}" fill-opacity="0.55"/>')
    if standard and optimized:
        for k, (sx_, sy_) in standard.items():
            ox, oy = optimized.get(k, (sx_, sy_))
            a, b2 = p(sx_, sy_), p(ox, oy)
            if math.hypot(a[0] - b2[0], a[1] - b2[1]) > 2:
                o.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b2[0]:.1f}" y2="{b2[1]:.1f}" stroke="{ACCENT}" stroke-width="1" stroke-dasharray="2 1.5"/>')
    if standard:
        for k, (x_, y_) in standard.items():
            x, y = p(x_, y_)
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#fff" stroke="{MUTED}" stroke-width="1"/>')
    if optimized:
        for k, (x_, y_) in optimized.items():
            x, y = p(x_, y_)
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{ACCENT}" stroke="#fff" stroke-width="1"/>')
            o.append(_t(x, y + 2.3, k, size=5.6, fill="#fff", weight=700))
    return _svg(w, h, "".join(o), "field")


# ------------------------------------------------------------------ small HTML helpers


def grade_chip(g: float | None, *, big: bool = False) -> str:
    from pitch_dataset.reports.grades import display_grade

    d = display_grade(g)
    if d is None:
        return '<span class="chip na">–</span>'
    bg = grade_color(g)
    return f'<span class="chip{" big" if big else ""}" style="background:{bg};color:{text_on(bg)}">{d}</span>'


def pct_bar(p: float | None, *, label: bool = True) -> str:
    """Percentile 0–100 (100 = best) as a thin bar with marker."""
    if p is None or not np.isfinite(p):
        return '<span class="pbar na"></span>'
    p = max(0.0, min(100.0, float(p)))
    c = div_color(p / 100)
    lab = f'<span class="pv">{p:.0f}</span>' if label else ""
    return (f'<span class="pbar"><span class="pfill" style="width:{p:.0f}%;background:{c}"></span>'
            f'<span class="pdot" style="left:{p:.0f}%;background:{c}"></span></span>{lab}')
