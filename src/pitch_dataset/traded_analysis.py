"""Pre/post trade-deadline pitcher analysis: usage, shape metrics, pairing/tunnel."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pitch_dataset.arsenal import (
    EXCLUDED_PITCH_TYPES,
    SHAPE_METRIC_COLS,
    _euclidean_sep,
    arsenal_pitch_types,
    pairing_features_for_type,
    pairing_note_for_type,
    pitcher_arsenal_means,
    primary_pitch_type,
)

DEFAULT_TRADED_PITCHERS: list[dict[str, Any]] = [
    {
        "key": "skubal",
        "name": "Tarik Skubal",
        "pitcher_id": 669373,
        "from_team": "DET",
        "to_team": "LAD",
        "trade_date": "2026-08-01",
    },
    {
        "key": "gausman",
        "name": "Kevin Gausman",
        "pitcher_id": 592332,
        "from_team": "TOR",
        "to_team": "CHC",
        "trade_date": "2026-08-02",
    },
    {
        "key": "soriano",
        "name": "José Soriano",
        "pitcher_id": 667755,
        "from_team": "LAA",
        "to_team": "TOR",
        "trade_date": "2026-08-03",
    },
    {
        "key": "mize",
        "name": "Casey Mize",
        "pitcher_id": 663554,
        "from_team": "DET",
        "to_team": "SD",
        "trade_date": "2026-08-03",
    },
    {
        "key": "peralta",
        "name": "Freddy Peralta",
        "pitcher_id": 642547,
        "from_team": "NYM",
        "to_team": "TB",
        "trade_date": "2026-08-02",
    },
]

SHAPE_METRIC_LABELS: dict[str, str] = {
    "release_speed": "Release speed (mph)",
    "effective_speed": "Effective speed (mph)",
    "release_extension": "Extension (ft)",
    "release_spin_rate": "Spin rate (rpm)",
    "spin_axis": "Spin axis (deg)",
    "arm_angle": "Arm angle (deg)",
    "release_pos_x": "Release side X (ft)",
    "release_pos_y": "Release depth Y (ft)",
    "release_pos_z": "Release height Z (ft)",
    "pfx_x": "PFX horizontal (in)",
    "pfx_z": "PFX vertical (in)",
    "api_break_x_arm": "Break X arm (in)",
    "api_break_x_batter_in": "Break X batter-in (in)",
    "api_break_z_with_gravity": "Break Z w/ gravity (in)",
}

PITCH_NAMES: dict[str, str] = {
    "FF": "4-Seam",
    "SI": "Sinker",
    "SL": "Slider",
    "CH": "Changeup",
    "CU": "Curveball",
    "KC": "Knuckle Curve",
    "ST": "Sweeper",
    "FC": "Cutter",
    "FS": "Splitter",
    "SV": "Slurve",
    "CS": "Slow Curve",
}


@dataclass
class PairingMetric:
    pitch_type: str
    primary: str
    velo_sep: float
    mov_sep: float
    release_dist_ft: float
    release_sim: float
    tunnel: str
    eff_speed_sep: float = 0.0
    spin_sep: float = 0.0
    spin_axis_sep: float = 0.0
    arm_sep: float = 0.0
    extension_sep: float = 0.0
    break_sep: float = 0.0
    note: str = ""


@dataclass
class TradedPitcherAnalysis:
    key: str
    name: str
    pitcher_id: int
    player_name: str
    from_team: str
    to_team: str
    trade_date: str
    n_total: int
    n_pre: int
    n_post: int
    pre_date_range: tuple[str, str] | None
    post_date_range: tuple[str, str] | None
    usage_pre: dict[str, float]
    usage_post: dict[str, float]
    shape_pre: dict[str, dict[str, float | None]]
    shape_post: dict[str, dict[str, float | None]]
    pairing_pre: list[PairingMetric]
    pairing_post: list[PairingMetric]
    primary_pre: str | None
    primary_post: str | None
    overall_shape: dict[str, float] = field(default_factory=dict)


def derive_pitcher_team(df: pd.DataFrame) -> pd.Series:
    """Pitcher's team from inning half + home/away (Statcast has no team field)."""
    top = df["inning_topbot"].astype(str).str.strip().str.lower().eq("top")
    return np.where(top, df["home_team"], df["away_team"])


def _prepare_frame(pitches: pd.DataFrame) -> pd.DataFrame:
    out = pitches.copy()
    if "game_date" in out.columns:
        out["game_date"] = pd.to_datetime(out["game_date"])
    out["pitcher_team"] = derive_pitcher_team(out)
    out = out[out["pitch_type"].notna()].copy()
    out["pitch_type"] = out["pitch_type"].astype(str).str.strip().str.upper()
    out = out[~out["pitch_type"].isin(EXCLUDED_PITCH_TYPES)].copy()
    for col in SHAPE_METRIC_COLS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _usage_mix(sub: pd.DataFrame, *, min_n: int) -> dict[str, float]:
    pts = arsenal_pitch_types(sub, min_n=min_n)
    if not pts:
        pts = sub["pitch_type"].value_counts().head(6).index.tolist()
    counts = sub["pitch_type"].value_counts()
    total = int(counts.sum())
    if total == 0:
        return {}
    return {pt: round(100 * counts.get(pt, 0) / total, 1) for pt in pts}


def _shape_table(sub: pd.DataFrame, *, min_n: int) -> dict[str, dict[str, float | None]]:
    pts = arsenal_pitch_types(sub, min_n=min_n)
    if not pts:
        pts = sub["pitch_type"].value_counts().head(6).index.tolist()
    subset = sub[sub["pitch_type"].isin(pts)]
    if subset.empty:
        return {}
    grouped = subset.groupby("pitch_type")[SHAPE_METRIC_COLS].mean(numeric_only=True)
    out: dict[str, dict[str, float | None]] = {}
    for pt in pts:
        if pt not in grouped.index:
            continue
        out[pt] = {
            col: round(float(grouped.loc[pt, col]), 2)
            if pd.notna(grouped.loc[pt, col])
            else None
            for col in SHAPE_METRIC_COLS
            if col in grouped.columns
        }
    return out


def compute_pairing_metrics(
    sub: pd.DataFrame,
    *,
    min_n: int = 15,
) -> tuple[list[PairingMetric], str | None]:
    """Pairing/tunnel metrics using shared ``arsenal`` helpers."""
    pts = arsenal_pitch_types(sub, min_n=min_n)
    if len(pts) < 2:
        pts = arsenal_pitch_types(sub, min_n=5)
    if not pts or sub.empty:
        return [], None

    means = pitcher_arsenal_means(sub)
    primary = primary_pitch_type(sub)
    if means.empty or primary is None or primary not in means.index:
        return [], None

    rel_cols = [c for c in ("release_pos_x", "release_pos_y", "release_pos_z") if c in means.columns]
    pairs: list[PairingMetric] = []
    for pt in pts:
        if pt == primary or pt not in means.index:
            continue
        feats = pairing_features_for_type(means, primary, pt)
        pri = means.loc[primary]
        row = means.loc[pt]
        rel = 0.0
        if rel_cols:
            rel = _euclidean_sep(row, pri, rel_cols)
        tunnel = (
            "strong tunnel"
            if rel < 0.25
            else ("moderate tunnel" if rel < 0.45 else "distinct release")
        )
        pairs.append(
            PairingMetric(
                pitch_type=pt,
                primary=primary,
                velo_sep=round(feats["pair_velo_sep"], 1),
                mov_sep=round(feats["pair_mov_sep"], 1),
                release_dist_ft=round(rel, 2),
                release_sim=round(feats["pair_release_sim"], 3),
                tunnel=tunnel,
                eff_speed_sep=round(feats["pair_eff_speed_sep"], 1),
                spin_sep=round(feats["pair_spin_sep"], 0),
                spin_axis_sep=round(feats["pair_spin_axis_sep"], 0),
                arm_sep=round(feats["pair_arm_sep"], 1),
                extension_sep=round(feats["pair_extension_sep"], 2),
                break_sep=round(feats["pair_break_sep"], 1),
                note=pairing_note_for_type(means, primary, pt),
            )
        )
    return pairs, primary


def analyze_traded_pitcher(
    pitches: pd.DataFrame,
    *,
    key: str,
    name: str,
    pitcher_id: int,
    from_team: str,
    to_team: str,
    trade_date: str,
    pre_min_n: int = 15,
    post_min_n: int = 5,
) -> TradedPitcherAnalysis | None:
    frame = _prepare_frame(pitches)
    sub = frame[frame["pitcher"] == pitcher_id].copy()
    if sub.empty:
        return None

    trade_ts = pd.Timestamp(trade_date)
    pre = sub[sub["game_date"] < trade_ts]
    post = sub[sub["game_date"] >= trade_ts]

    pairing_pre, primary_pre = compute_pairing_metrics(pre, min_n=pre_min_n)
    pairing_post, primary_post = compute_pairing_metrics(post, min_n=post_min_n)

    pre_range = None
    if len(pre):
        pre_range = (str(pre["game_date"].min().date()), str(pre["game_date"].max().date()))
    post_range = None
    if len(post):
        post_range = (str(post["game_date"].min().date()), str(post["game_date"].max().date()))

    overall_shape: dict[str, float] = {}
    for col in SHAPE_METRIC_COLS:
        if col in sub.columns and sub[col].notna().any():
            overall_shape[col] = round(float(sub[col].mean()), 2)

    return TradedPitcherAnalysis(
        key=key,
        name=name,
        pitcher_id=pitcher_id,
        player_name=str(sub["player_name"].iloc[0]),
        from_team=from_team,
        to_team=to_team,
        trade_date=trade_date,
        n_total=int(len(sub)),
        n_pre=int(len(pre)),
        n_post=int(len(post)),
        pre_date_range=pre_range,
        post_date_range=post_range,
        usage_pre=_usage_mix(pre, min_n=pre_min_n),
        usage_post=_usage_mix(post, min_n=post_min_n),
        shape_pre=_shape_table(pre, min_n=pre_min_n),
        shape_post=_shape_table(post, min_n=post_min_n),
        pairing_pre=pairing_pre,
        pairing_post=pairing_post,
        primary_pre=primary_pre,
        primary_post=primary_post,
        overall_shape=overall_shape,
    )


def analyze_traded_pitchers(
    pitches: pd.DataFrame,
    *,
    configs: list[dict[str, Any]] | None = None,
    keys: list[str] | None = None,
) -> list[TradedPitcherAnalysis]:
    configs = configs or DEFAULT_TRADED_PITCHERS
    if keys:
        key_set = {k.strip().lower() for k in keys}
        configs = [c for c in configs if c["key"] in key_set]
    results: list[TradedPitcherAnalysis] = []
    for cfg in configs:
        analysis = analyze_traded_pitcher(pitches, **cfg)
        if analysis is not None:
            results.append(analysis)
    return results


def _pitch_label(pt: str) -> str:
    name = PITCH_NAMES.get(pt, pt)
    return f"{pt} · {name}"


def _usage_delta(pre: dict[str, float], post: dict[str, float]) -> list[tuple[str, float, float, float]]:
    pts = sorted(set(pre) | set(post), key=lambda p: pre.get(p, post.get(p, 0)), reverse=True)
    return [(pt, pre.get(pt, 0.0), post.get(pt, 0.0), post.get(pt, 0.0) - pre.get(pt, 0.0)) for pt in pts]


def format_traded_report(
    analyses: list[TradedPitcherAnalysis],
    *,
    title: str = "2026 Trade Deadline Pitcher Analysis",
    data_note: str | None = None,
) -> str:
    lines: list[str] = [f"# {title}", ""]
    if data_note:
        lines.extend([data_note, ""])

    lines.extend(
        [
            "Pre/post splits use **trade date** cutoffs and **pitcher team** derived from "
            "`inning_topbot` + home/away. Shape metrics cover arm angle, spin, extension, "
            "effective speed, release point, movement, and API break. Pairing/tunnel notes "
            "reuse extended separation logic from `arsenal.py` (velo/movement, effective "
            "speed, spin, arm angle, extension, API break, 3D release distance).",
            "",
        ]
    )

    for rec in analyses:
        lines.extend(_format_pitcher_section(rec))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_pitcher_section(rec: TradedPitcherAnalysis) -> list[str]:
    lines = [
        f"## {rec.name} ({rec.from_team} → {rec.to_team})",
        "",
        f"- MLBAM **{rec.pitcher_id}** · trade date **{rec.trade_date}**",
        f"- Pitches: **{rec.n_pre:,}** pre / **{rec.n_post:,}** post "
        f"(total {rec.n_total:,})",
    ]
    if rec.pre_date_range:
        lines.append(f"- Pre-trade window: {rec.pre_date_range[0]} → {rec.pre_date_range[1]}")
    if rec.post_date_range:
        lines.append(f"- Post-trade window: {rec.post_date_range[0]} → {rec.post_date_range[1]}")
    if rec.n_post < 50:
        lines.append(
            f"- _Note: post-trade sample is small (n={rec.n_post}); treat shifts as directional._"
        )
    lines.append("")

    lines.extend(["### Usage mix (%)", ""])
    lines.append("| Pitch | Pre | Post | Δ pp |")
    lines.append("| --- | ---: | ---: | ---: |")
    for pt, pre_pct, post_pct, delta in _usage_delta(rec.usage_pre, rec.usage_post):
        sign = "+" if delta >= 0 else ""
        lines.append(f"| {_pitch_label(pt)} | {pre_pct:.1f} | {post_pct:.1f} | {sign}{delta:.1f} |")
    lines.append("")

    primary_note = ""
    if rec.primary_pre != rec.primary_post:
        primary_note = (
            f" Primary pitch shifted **{rec.primary_pre} → {rec.primary_post}** post-trade."
        )
    lines.extend(["### Pairing / tunnel vs primary", "", primary_note.strip(), ""])
    if rec.pairing_pre:
        lines.append("**Pre-trade**")
        for pair in rec.pairing_pre:
            lines.append(f"- {pair.note}")
        lines.append("")
    if rec.pairing_post:
        lines.append("**Post-trade**")
        for pair in rec.pairing_post:
            lines.append(f"- {pair.note}")
        lines.append("")

    lines.extend(["### Shape metrics by pitch type", ""])
    shape_pts = sorted(set(rec.shape_pre) | set(rec.shape_post))
    highlight_cols = [
        "arm_angle",
        "release_pos_z",
        "release_extension",
        "release_spin_rate",
        "effective_speed",
        "api_break_z_with_gravity",
    ]
    for pt in shape_pts:
        lines.append(f"#### {_pitch_label(pt)}")
        lines.append("")
        lines.append("| Metric | Pre | Post | Δ |")
        lines.append("| --- | ---: | ---: | ---: |")
        pre_row = rec.shape_pre.get(pt, {})
        post_row = rec.shape_post.get(pt, {})
        cols = highlight_cols + [c for c in SHAPE_METRIC_COLS if c not in highlight_cols]
        for col in cols:
            if col not in pre_row and col not in post_row:
                continue
            pre_v = pre_row.get(col)
            post_v = post_row.get(col)
            if pre_v is None and post_v is None:
                continue
            delta = None
            if pre_v is not None and post_v is not None:
                delta = post_v - pre_v
            label = SHAPE_METRIC_LABELS.get(col, col)
            pre_s = f"{pre_v:.2f}" if pre_v is not None else "—"
            post_s = f"{post_v:.2f}" if post_v is not None else "—"
            if delta is None:
                delta_s = "—"
            else:
                delta_s = f"{delta:+.2f}"
            lines.append(f"| {label} | {pre_s} | {post_s} | {delta_s} |")
        lines.append("")

    return lines


def write_traded_report(
    analyses: list[TradedPitcherAnalysis],
    path: Path | str,
    **kwargs,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_traded_report(analyses, **kwargs), encoding="utf-8")
    return path


def analysis_to_dict(analyses: list[TradedPitcherAnalysis]) -> dict[str, Any]:
    payload = []
    for rec in analyses:
        d = asdict(rec)
        d["pairing_pre"] = [asdict(p) for p in rec.pairing_pre]
        d["pairing_post"] = [asdict(p) for p in rec.pairing_post]
        payload.append(d)
    return {"pitchers": payload}


def write_traded_json(analyses: list[TradedPitcherAnalysis], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(analysis_to_dict(analyses), indent=2), encoding="utf-8")
    return path


def _fmt_num(value: float | None, *, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return f"{value:.{decimals}f}"


def _fmt_delta(pre: float | None, post: float | None, *, decimals: int = 2) -> str:
    if pre is None or post is None:
        return "—"
    if isinstance(pre, float) and np.isnan(pre):
        return "—"
    if isinstance(post, float) and np.isnan(post):
        return "—"
    return f"{post - pre:+.{decimals}f}"


def _pairing_lookup(pairs: list[PairingMetric]) -> dict[str, PairingMetric]:
    return {p.pitch_type: p for p in pairs}


PAIRING_DELTA_ROWS: list[tuple[str, str, int]] = [
    ("velo_sep", "Velo sep (mph)", 1),
    ("mov_sep", "Move sep (in)", 1),
    ("eff_speed_sep", "Eff speed sep (mph)", 1),
    ("spin_sep", "Spin sep (rpm)", 0),
    ("spin_axis_sep", "Spin axis sep (deg)", 0),
    ("arm_sep", "Arm angle sep (deg)", 1),
    ("extension_sep", "Extension sep (ft)", 2),
    ("break_sep", "API break sep (in)", 1),
    ("release_dist_ft", "Release dist (ft)", 2),
]


def _pairing_delta_html(pre: list[PairingMetric], post: list[PairingMetric]) -> str:
    pre_map = _pairing_lookup(pre)
    post_map = _pairing_lookup(post)
    secondaries = sorted(set(pre_map) | set(post_map))
    if not secondaries:
        return ""

    rows: list[str] = []
    for pt in secondaries:
        pre_row = pre_map.get(pt)
        post_row = post_map.get(pt)
        for field, label, decimals in PAIRING_DELTA_ROWS:
            pre_v = getattr(pre_row, field, None) if pre_row else None
            post_v = getattr(post_row, field, None) if post_row else None
            if pre_v is None and post_v is None:
                continue
            rows.append(
                "<tr>"
                f"<td>{_pitch_label(pt)}</td>"
                f"<td>{label}</td>"
                f"<td>{_fmt_num(pre_v, decimals=decimals)}</td>"
                f"<td>{_fmt_num(post_v, decimals=decimals)}</td>"
                f"<td>{_fmt_delta(pre_v, post_v, decimals=decimals)}</td>"
                "</tr>"
            )
    if not rows:
        return ""
    return (
        "<table><thead><tr><th>Secondary</th><th>Metric</th><th>Pre</th><th>Post</th><th>Δ</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _shape_sections_html(rec: TradedPitcherAnalysis) -> str:
    highlight_cols = [
        "arm_angle",
        "release_pos_z",
        "release_extension",
        "release_spin_rate",
        "effective_speed",
        "api_break_z_with_gravity",
    ]
    cols = highlight_cols + [c for c in SHAPE_METRIC_COLS if c not in highlight_cols]
    shape_pts = sorted(set(rec.shape_pre) | set(rec.shape_post))
    blocks: list[str] = []
    for pt in shape_pts:
        pre_row = rec.shape_pre.get(pt, {})
        post_row = rec.shape_post.get(pt, {})
        metric_rows: list[str] = []
        for col in cols:
            if col not in pre_row and col not in post_row:
                continue
            pre_v = pre_row.get(col)
            post_v = post_row.get(col)
            if pre_v is None and post_v is None:
                continue
            decimals = 0 if col == "release_spin_rate" else 2
            metric_rows.append(
                "<tr>"
                f"<td>{SHAPE_METRIC_LABELS.get(col, col)}</td>"
                f"<td>{_fmt_num(pre_v, decimals=decimals)}</td>"
                f"<td>{_fmt_num(post_v, decimals=decimals)}</td>"
                f"<td>{_fmt_delta(pre_v, post_v, decimals=decimals)}</td>"
                "</tr>"
            )
        if not metric_rows:
            continue
        blocks.append(
            f"<details open><summary>{_pitch_label(pt)}</summary>"
            "<table><thead><tr><th>Metric</th><th>Pre</th><th>Post</th><th>Δ</th></tr></thead>"
            f"<tbody>{''.join(metric_rows)}</tbody></table></details>"
        )
    return "".join(blocks)


def write_traded_html(
    analyses: list[TradedPitcherAnalysis],
    path: Path | str,
    *,
    data_note: str | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    note = data_note or (
        "MLB Statcast pitches · team derived from inning half + home/away · "
        "pre/post split at trade date"
    )
    sections: list[str] = []
    nav_links: list[str] = []

    for rec in analyses:
        anchor = rec.key
        nav_links.append(f'<a href="#{anchor}">{rec.name.split()[-1]}</a>')
        usage_rows = []
        max_pct = 1.0
        for pt, pre_pct, post_pct, delta in _usage_delta(rec.usage_pre, rec.usage_post):
            max_pct = max(max_pct, pre_pct, post_pct)
            delta_cls = "pos" if delta >= 0 else "neg"
            usage_rows.append(
                f'<div class="row"><div>{_pitch_label(pt)}</div>'
                f'<div class="bars"><div class="bar pre" style="width:{pre_pct / max_pct * 100:.1f}%"></div>'
                f'<div class="bar post" style="width:{post_pct / max_pct * 100:.1f}%"></div></div>'
                f'<div class="{delta_cls}">{delta:+.1f}</div></div>'
            )

        pairing_html = []
        if rec.pairing_pre:
            pairing_html.append("<p><strong>Pre-trade</strong></p><ul class=\"pair\">")
            pairing_html.extend(f"<li>{p.note}</li>" for p in rec.pairing_pre)
            pairing_html.append("</ul>")
        if rec.pairing_post:
            pairing_html.append("<p><strong>Post-trade</strong></p><ul class=\"pair\">")
            pairing_html.extend(f"<li>{p.note}</li>" for p in rec.pairing_post)
            pairing_html.append("</ul>")

        pairing_delta = _pairing_delta_html(rec.pairing_pre, rec.pairing_post)
        shape_sections = _shape_sections_html(rec)

        primary_shift = ""
        if rec.primary_pre != rec.primary_post:
            primary_shift = (
                f'<p class="meta">Primary pitch: <strong>{rec.primary_pre}</strong> → '
                f"<strong>{rec.primary_post}</strong></p>"
            )

        sample_note = ""
        if rec.n_post < 50:
            sample_note = (
                f'<p class="meta">Post-trade n={rec.n_post} — small sample; read shifts as directional.</p>'
            )

        sections.append(
            f"""
<section id="{anchor}" class="pitcher">
  <h2>{rec.name} · {rec.from_team} → {rec.to_team}</h2>
  <p class="meta">Trade {rec.trade_date} · MLBAM {rec.pitcher_id} · {rec.n_pre:,} pre / {rec.n_post:,} post pitches</p>
  {sample_note}
  {primary_shift}
  <div class="hero">
    <div class="stat"><div class="v">{rec.primary_pre or '—'} → {rec.primary_post or '—'}</div><div class="l">Primary pitch</div></div>
    <div class="stat"><div class="v">{rec.overall_shape.get('arm_angle', 0):.1f}°</div><div class="l">Season arm angle</div></div>
    <div class="stat"><div class="v">{rec.overall_shape.get('release_extension', 0):.2f} ft</div><div class="l">Season extension</div></div>
    <div class="stat"><div class="v">{rec.n_post:,}</div><div class="l">Post-trade pitches</div></div>
  </div>
  <h3>Usage mix pre vs post (%)</h3>
  <div class="chart">
    <div class="legend">
      <span><span class="swatch pre"></span>Pre-trade</span>
      <span><span class="swatch post"></span>Post-trade</span>
    </div>
    {''.join(usage_rows)}
    <div class="axis"><span>Pitch type</span><span>Share (bar scale normalized to max mix)</span></div>
  </div>
  <h3>Pairing / tunnel notes</h3>
  {''.join(pairing_html)}
  <h3>Pairing metrics pre vs post (vs primary)</h3>
  {pairing_delta}
  <h3>Shape metrics by pitch type</h3>
  <div class="shape-groups">{shape_sections}</div>
</section>
"""
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>2026 Trade Deadline Pitcher Analysis</title>
  <style>
    :root {{
      --bg: #f7f7f5; --fg: #1a1a1a; --muted: #5c5c5c; --line: #d8d8d4;
      --accent: #1f4b99; --good: #1f6b3a; --card: #ffffff;
      --bar-pre: #8a8a84; --bar-post: #1f4b99;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 15px/1.45 "IBM Plex Sans", "Segoe UI", sans-serif; color: var(--fg); background: var(--bg); }}
    main {{ max-width: 960px; margin: 0 auto; padding: 40px 24px 64px; }}
    h1 {{ font: 600 28px/1.2 sans-serif; margin: 0 0 8px; letter-spacing: -0.02em; }}
    h2 {{ font: 600 20px/1.3 sans-serif; margin: 40px 0 10px; padding-top: 8px; border-top: 1px solid var(--line); }}
    h2:first-of-type {{ border-top: 0; margin-top: 24px; }}
    h3 {{ font: 600 15px/1.3 sans-serif; margin: 24px 0 8px; }}
    p, .meta {{ color: var(--muted); margin: 0 0 12px; }}
    nav {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0 24px; }}
    nav a {{ color: var(--accent); text-decoration: none; font-size: 14px; padding: 6px 10px; border: 1px solid var(--line); border-radius: 4px; background: var(--card); }}
    .hero {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }}
    .stat {{ background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; }}
    .stat .v {{ font: 600 18px/1.2 sans-serif; color: var(--accent); }}
    .stat .l {{ margin-top: 4px; font-size: 12px; color: var(--muted); }}
    .chart {{ background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 16px 18px 12px; }}
    .row {{ display: grid; grid-template-columns: 120px 1fr 52px; gap: 8px; align-items: center; margin: 8px 0; font-size: 13px; }}
    .bars {{ position: relative; height: 28px; }}
    .bar {{ position: absolute; left: 0; height: 11px; border-radius: 2px; }}
    .bar.pre {{ top: 2px; background: var(--bar-pre); }}
    .bar.post {{ bottom: 2px; background: var(--bar-post); }}
    .legend {{ display: flex; gap: 16px; font-size: 12px; color: var(--muted); margin-bottom: 8px; }}
    .swatch {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }}
    .swatch.pre {{ background: var(--bar-pre); }}
    .swatch.post {{ background: var(--bar-post); }}
    table {{ width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; font-size: 13px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: right; }}
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
    th {{ background: #efefeb; font-weight: 600; font-size: 12px; }}
    tr:last-child td {{ border-bottom: 0; }}
    ul.pair {{ margin: 0 0 12px; padding-left: 18px; color: var(--muted); font-size: 13px; }}
    .shape-groups details {{ margin: 12px 0; background: var(--card); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }}
    .shape-groups summary {{ cursor: pointer; padding: 10px 12px; font-weight: 600; font-size: 13px; background: #efefeb; }}
    .shape-groups details table {{ border: 0; border-radius: 0; margin: 0; }}
    .neg {{ color: var(--good); }}
    .pos {{ color: var(--accent); }}
    .caption {{ margin-top: 8px; font-size: 12px; color: var(--muted); }}
    @media (max-width: 720px) {{ .hero {{ grid-template-columns: 1fr 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <h1>2026 Trade Deadline Pitcher Analysis</h1>
    <p class="meta">{note}</p>
    <nav>{''.join(nav_links)}</nav>
    {''.join(sections)}
    <p class="caption">Source: pitch-dataset traded analysis · pairing/tunnel logic from arsenal.py</p>
  </main>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    return path


SHAPE_FOCUS_COLS: list[str] = [
    "arm_angle",
    "release_spin_rate",
    "release_extension",
    "effective_speed",
    "api_break_z_with_gravity",
    "api_break_x_arm",
    "api_break_x_batter_in",
]


def _shape_focus_table_html(rec: TradedPitcherAnalysis) -> str:
    """Compact shape delta table for the five headline Statcast fields."""
    shape_pts = sorted(set(rec.shape_pre) | set(rec.shape_post))
    rows: list[str] = []
    for pt in shape_pts:
        pre_row = rec.shape_pre.get(pt, {})
        post_row = rec.shape_post.get(pt, {})
        for col in SHAPE_FOCUS_COLS:
            pre_v = pre_row.get(col)
            post_v = post_row.get(col)
            if pre_v is None and post_v is None:
                continue
            decimals = 0 if col == "release_spin_rate" else 2
            rows.append(
                "<tr>"
                f"<td>{_pitch_label(pt)}</td>"
                f"<td>{SHAPE_METRIC_LABELS.get(col, col)}</td>"
                f"<td>{_fmt_num(pre_v, decimals=decimals)}</td>"
                f"<td>{_fmt_num(post_v, decimals=decimals)}</td>"
                f"<td>{_fmt_delta(pre_v, post_v, decimals=decimals)}</td>"
                "</tr>"
            )
    if not rows:
        return "<p class=\"meta\">No shape metrics in sample.</p>"
    return (
        "<table><thead><tr><th>Pitch</th><th>Metric</th><th>Pre</th><th>Post</th><th>Δ</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _pairing_table_html(pairs: list[PairingMetric], primary: str | None) -> str:
    if not pairs:
        return "<p class=\"meta\">No pairing rows for this period.</p>"
    pri = primary or "—"
    rows: list[str] = []
    for p in pairs:
        rows.append(
            "<tr>"
            f"<td>{_pitch_label(p.pitch_type)}</td>"
            f"<td>{p.velo_sep:.1f}</td>"
            f"<td>{p.mov_sep:.1f}</td>"
            f"<td>{p.eff_speed_sep:.1f}</td>"
            f"<td>{p.spin_sep:.0f}</td>"
            f"<td>{p.arm_sep:.1f}</td>"
            f"<td>{p.extension_sep:.2f}</td>"
            f"<td>{p.break_sep:.1f}</td>"
            f"<td>{p.release_dist_ft:.2f}</td>"
            f"<td>{p.tunnel}</td>"
            "</tr>"
        )
    return (
        f"<p class=\"meta\">vs primary <strong>{pri}</strong></p>"
        "<table><thead><tr>"
        "<th>Secondary</th><th>Velo</th><th>Move</th><th>Eff spd</th>"
        "<th>Spin</th><th>Arm</th><th>Ext</th><th>Break</th><th>Rel dist</th><th>Tunnel</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def write_traded_shape_html(
    analyses: list[TradedPitcherAnalysis],
    path: Path | str,
    *,
    data_note: str | None = None,
) -> Path:
    """Self-contained shape + pairing visual with pitcher switcher (distinct from usage HTML)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    note = data_note or (
        "MLB Statcast · arm angle, spin, extension, effective speed, API break · "
        "extended pairing/tunnel vs primary"
    )

    payload: list[dict[str, Any]] = []
    panels: list[str] = []
    for i, rec in enumerate(analyses):
        shape_delta = _shape_focus_table_html(rec)
        pairing_delta = _pairing_delta_html(rec.pairing_pre, rec.pairing_post)
        pairing_pre = _pairing_table_html(rec.pairing_pre, rec.primary_pre)
        pairing_post = _pairing_table_html(rec.pairing_post, rec.primary_post)
        primary_shift = ""
        if rec.primary_pre != rec.primary_post:
            primary_shift = (
                f"Primary: {rec.primary_pre} → {rec.primary_post} · "
            )
        hidden = "" if i == 0 else ' style="display:none"'

        panels.append(
            f"""
<article class="pitcher-panel" data-key="{rec.key}"{hidden}>
  <header class="panel-head">
    <h2>{rec.name}</h2>
    <p class="meta">{rec.from_team} → {rec.to_team} · trade {rec.trade_date} · MLBAM {rec.pitcher_id}</p>
    <p class="meta">{rec.n_pre:,} pre / {rec.n_post:,} post pitches · {primary_shift}season arm {rec.overall_shape.get('arm_angle', 0):.1f}° · ext {rec.overall_shape.get('release_extension', 0):.2f} ft</p>
  </header>
  <div class="grid-2">
    <section>
      <h3>Shape deltas (pre vs post)</h3>
      <p class="section-note">Arm angle · spin · extension · effective speed · API break by pitch type</p>
      {shape_delta}
    </section>
    <section>
      <h3>Pairing deltas vs primary</h3>
      <p class="section-note">Spin/arm/extension/break separation and 3D release tunnel distance</p>
      {pairing_delta or '<p class="meta">No overlapping secondaries across periods.</p>'}
    </section>
  </div>
  <div class="grid-2">
    <section>
      <h3>Pre-trade pairing</h3>
      {pairing_pre}
    </section>
    <section>
      <h3>Post-trade pairing</h3>
      {pairing_post}
    </section>
  </div>
</article>
"""
        )

        d = asdict(rec)
        d["pairing_pre"] = [asdict(p) for p in rec.pairing_pre]
        d["pairing_post"] = [asdict(p) for p in rec.pairing_post]
        payload.append(d)

    options = "".join(
        f'<option value="{rec.key}"{" selected" if i == 0 else ""}>{rec.name} ({rec.from_team} → {rec.to_team})</option>'
        for i, rec in enumerate(analyses)
    )
    data_json = json.dumps(payload).replace("</", "<\\/")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>2026 Trade Deadline · Shape &amp; Pairing Lab</title>
  <style>
    :root {{
      --bg: #0f1419; --fg: #e8eaed; --muted: #9aa0a6; --line: #2d333b;
      --accent: #3dd6c6; --accent-dim: #1a4f4a; --card: #161b22;
      --pre: #8b949e; --post: #3dd6c6; --warn: #d4a574;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 15px/1.5 "IBM Plex Sans", "Segoe UI", sans-serif; color: var(--fg); background: var(--bg); }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px 64px; }}
    .brand {{ display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }}
    .brand-tag {{ font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); border: 1px solid var(--accent-dim); padding: 3px 8px; border-radius: 3px; }}
    h1 {{ font: 600 26px/1.2 sans-serif; margin: 0; letter-spacing: -0.02em; }}
    h2 {{ font: 600 20px/1.3 sans-serif; margin: 0 0 6px; }}
    h3 {{ font: 600 14px/1.3 sans-serif; margin: 0 0 8px; color: var(--accent); }}
    p, .meta {{ color: var(--muted); margin: 0 0 10px; font-size: 13px; }}
    .section-note {{ font-size: 12px; margin-bottom: 12px; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 20px 0 28px; padding: 14px 16px; background: var(--card); border: 1px solid var(--line); border-radius: 8px; }}
    .controls label {{ font-size: 13px; color: var(--muted); }}
    select {{ font: inherit; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg); color: var(--fg); min-width: 280px; }}
    .pitcher-panel {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 20px 22px 24px; }}
    .panel-head {{ border-bottom: 1px solid var(--line); padding-bottom: 14px; margin-bottom: 20px; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: right; }}
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
    th {{ color: var(--muted); font-weight: 600; font-size: 11px; }}
    tr:last-child td {{ border-bottom: 0; }}
    .delta-pos {{ color: var(--accent); }}
    .delta-neg {{ color: var(--warn); }}
    .caption {{ margin-top: 24px; font-size: 12px; color: var(--muted); }}
    .metric-bars {{ margin: 16px 0 24px; }}
    .metric-row {{ display: grid; grid-template-columns: 140px 1fr 1fr 56px; gap: 8px; align-items: center; margin: 6px 0; font-size: 12px; }}
    .metric-row .lbl {{ color: var(--muted); }}
    .bar-track {{ height: 8px; background: var(--line); border-radius: 2px; position: relative; }}
    .bar-fill {{ height: 100%; border-radius: 2px; }}
    .bar-fill.pre {{ background: var(--pre); }}
    .bar-fill.post {{ background: var(--post); }}
    @media (max-width: 860px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <div class="brand">
      <span class="brand-tag">Shape · Pairing</span>
      <h1>2026 Trade Deadline · Shape &amp; Pairing Lab</h1>
    </div>
    <p class="meta">{note}</p>
    <div class="controls">
      <label for="pitcher-select">Pitcher</label>
      <select id="pitcher-select" aria-label="Select traded pitcher">{options}</select>
    </div>
    <div id="panels">{''.join(panels)}</div>
    <p class="caption">Source: pitch-dataset traded analysis · extended pairing from arsenal.py (spin/arm/extension/break/release tunnel)</p>
  </main>
  <script id="shape-data" type="application/json">{data_json}</script>
  <script>
    (function () {{
      var select = document.getElementById('pitcher-select');
      var panels = document.querySelectorAll('.pitcher-panel');
      select.addEventListener('change', function () {{
        var key = select.value;
        panels.forEach(function (p) {{
          p.style.display = p.getAttribute('data-key') === key ? '' : 'none';
        }});
      }});
    }})();
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    return path
