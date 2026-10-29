"""Report generation service shared by the CLI, the select-web app, and the portfolio build."""

from __future__ import annotations

import json
import logging
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pitch_dataset.reports import render as R
from pitch_dataset.reports.context import (
    FG_TEAM_TO_MLB,
    LeagueContext,
    build_league_context,
)
from pitch_dataset.reports.grades import display_grade
from pitch_dataset.reports.models import load_models
from pitch_dataset.reports.svg import ACCENT, esc, grade_chip
from pitch_dataset.storage import mlb_api_path

log = logging.getLogger(__name__)

MIN_REPORT_PITCHES = 300  # pitches thrown (pitchers) or seen (hitters) for a report to be generated
KINDS = ("pitcher", "batter")


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower().strip()


def player_index(ctx: LeagueContext) -> pd.DataFrame:
    """Every pitcher / batter in the context with name, team, sample and headline grades."""
    rows = []
    for kind, table, grade_cols in (("pitcher", ctx.pitchers, ("g_stuff", "g_command")),
                                    ("batter", ctx.batters, ("g_hit", "g_power"))):
        for pid, r in table.iterrows():
            rows.append({
                "kind": kind, "id": int(pid), "name": ctx.name(pid), "fg_name": str(r.get("fg_name") or ""),
                "team": str(r.get("fg_team") or ""), "n": int(r["n"]), "qualified": bool(r.get("qualified", False)),
                "hand": str(r.get("p_throws") if kind == "pitcher" else r.get("stand")),
                "g1": display_grade(r.get(grade_cols[0])), "g2": display_grade(r.get(grade_cols[1])),
                "eligible": int(r["n"]) >= MIN_REPORT_PITCHES,
            })
    df = pd.DataFrame(rows)
    df["team"] = df["team"].where(~df["team"].str.startswith("-"), "")
    df["team"] = df["team"].replace(FG_TEAM_TO_MLB)
    path = mlb_api_path(ctx.data_dir, season=ctx.season, kind="rosters")
    if path.exists():
        r = pd.read_parquet(path, columns=["player_id", "team_abbr"]).drop_duplicates("player_id", keep="last")
        roster_team = df["id"].map(dict(zip(r["player_id"].astype(int), r["team_abbr"], strict=False)))
        df["team"] = roster_team.fillna(df["team"])
    return df


def resolve_player(ctx: LeagueContext, query: str | int, kind: str) -> int:
    """MLBAM id from an id or a (accent-insensitive) name; most pitches wins ties."""
    idx = player_index(ctx)
    idx = idx[idx["kind"] == kind]
    q = str(query).strip()
    if q.isdigit() and int(q) in set(idx["id"]):
        return int(q)
    fq = _fold(q)
    names = idx["name"].map(_fold)
    fg = idx["fg_name"].map(_fold)
    for mask in (names.eq(fq) | fg.eq(fq), names.str.contains(fq, regex=False) | fg.str.contains(fq, regex=False)):
        hit = idx[mask]
        if len(hit):
            return int(hit.sort_values("n", ascending=False)["id"].iloc[0])
    raise LookupError(f"No {kind} matching {query!r} in the {ctx.season} regular season")


def team_roster(ctx: LeagueContext, team: str) -> dict[str, list[int]]:
    """Active-roster pitchers and hitters for a team (FanGraphs or MLB abbreviation) above the sample floor."""
    path = mlb_api_path(ctx.data_dir, season=ctx.season, kind="rosters")
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}; run `pitch-dataset pull-api` first")
    abbr = FG_TEAM_TO_MLB.get(team.upper(), team.upper())
    r = pd.read_parquet(path)
    r = r[(r["team_abbr"].str.upper() == abbr) & (r["status_code"] == "A")]
    if r.empty:
        raise LookupError(f"No active roster rows for team {team!r} (MLB abbr {abbr})")
    ids = set(r["player_id"].astype(int))
    pos = dict(zip(r["player_id"].astype(int), r["position_code"].astype(str), strict=False))
    pit, bat = ctx.pitchers, ctx.batters
    pitchers = [i for i in ids if i in pit.index and pit.loc[i, "n"] >= MIN_REPORT_PITCHES]
    hitters = [i for i in ids if i in bat.index and bat.loc[i, "n"] >= MIN_REPORT_PITCHES and pos.get(i) != "1"]
    pitchers.sort(key=lambda i: -pit.loc[i, "n"])
    hitters.sort(key=lambda i: -bat.loc[i, "n"])
    return {"pitcher": pitchers, "batter": hitters}


@dataclass
class ReportService:
    """Lazily loads the league context + models once; generates reports on demand (thread-safe)."""

    data_dir: Path = Path("data")
    models_dir: str = "models"
    season: int = 2026
    _ctx: LeagueContext | None = None
    _models: dict[str, Any] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def ctx(self) -> LeagueContext:
        if self._ctx is None:
            self._ctx = build_league_context(self.data_dir, self.season)
        return self._ctx

    @property
    def models(self) -> dict[str, Any]:
        if self._models is None:
            self._models = load_models(self.models_dir)
        return self._models

    def generate(self, kind: str, pid: int, out_dir: Path | str, *, pdf: bool = True,
                 screen_links: list[tuple[str, str]] | None = None) -> dict[str, Any]:
        from pitch_dataset.reports.hitter import build_hitter_data, render_hitter_html
        from pitch_dataset.reports.pitcher import (
            build_pitcher_data,
            render_pitcher_html,
        )

        with self._lock:
            ctx = self.ctx
            if kind == "pitcher":
                d = build_pitcher_data(ctx, pid, self.models)
                html = render_pitcher_html(d, screen_links=screen_links)
            elif kind == "batter":
                d = build_hitter_data(ctx, pid, self.models)
                html = render_hitter_html(d, screen_links=screen_links)
            else:
                raise ValueError(f"kind must be one of {KINDS}")
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        slug = R.slugify(d["name"])
        html_path = out / f"{slug}.html"
        html_path.write_text(html, encoding="utf-8")
        pdf_path = out / f"{slug}.pdf" if pdf and R.html_to_pdf(html_path, out / f"{slug}.pdf") else None
        row = d["row"]
        meta = {
            "kind": kind, "id": int(pid), "name": d["name"], "slug": slug, "team": d["team"],
            "hand": d.get("hand_word") or {"L": "Bats L", "R": "Bats R", "S": "Switch"}[d["bats"]],
            "role": d.get("role", ""), "bullets": d["bullets"], "html": str(html_path),
            "pdf": str(pdf_path) if pdf_path else None, "through": ctx.date_range[1],
            "grades": _headline_grades(kind, row), "line": _headline_line(kind, row),
        }
        (out / f"{slug}.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
        return meta


def _headline_grades(kind: str, row: pd.Series) -> list[tuple[str, float | None]]:
    keys = ([("Stuff", "g_stuff"), ("Cmd", "g_command"), ("Miss", "g_miss"), ("Contact", "g_contact")]
            if kind == "pitcher" else
            [("Hit", "g_hit"), ("Power", "g_power"), ("Disc", "g_discipline"), ("Pull-air", "g_pull_air")])
    out = []
    for lab, k in keys:
        v = row.get(k)
        out.append((lab, float(v) if v is not None and np.isfinite(v) else None))
    return out


def _f(v: Any, fmt: str) -> str:
    try:
        return fmt.format(float(v)) if np.isfinite(float(v)) else "–"
    except (TypeError, ValueError):
        return "–"


def _headline_line(kind: str, row: pd.Series) -> str:
    if kind == "pitcher":
        return (f"{_f(row.get('IP'), '{:.1f}')} IP · {_f(row.get('ERA'), '{:.2f}')} ERA · "
                f"{_f(row.get('xERA'), '{:.2f}')} xERA · {_f(100 * row.get('K%', np.nan), '{:.1f}')}% K")
    return (f"{_f(row.get('PA'), '{:.0f}')} PA · {_f(row.get('wRC+'), '{:.0f}')} wRC+ · "
            f"{_f(row.get('xwOBA'), '{:.3f}').lstrip('0')} xwOBA · {_f(row.get('HR'), '{:.0f}')} HR")


# ------------------------------------------------------------------ index / gallery page

INDEX_CSS = """
*{box-sizing:border-box} body{margin:0;font-family:"Inter","Helvetica Neue",Helvetica,Arial,sans-serif;color:#1b1f24;
background:#f3f4f6;font-variant-numeric:tabular-nums}
.wrap{max-width:1180px;margin:0 auto;padding:22px 22px 40px}
.top{border-bottom:2.5px solid ACCENT;padding-bottom:10px;margin-bottom:16px}
.kicker{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:ACCENT;font-weight:700}
h1{margin:4px 0 4px;font-size:28px;letter-spacing:-.01em} .lede{color:#4b5563;font-size:14px;max-width:880px;line-height:1.5}
h2{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:ACCENT;margin:22px 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(355px,1fr));gap:14px}
.card{background:#fff;border:1px solid #dfe3e8;border-radius:6px;padding:14px 15px 12px;display:flex;flex-direction:column;
box-shadow:0 1px 2px rgba(0,0,0,.04)}
.card .hd{display:flex;gap:10px;align-items:center}
.badge{width:38px;height:38px;border-radius:50%;background:ACCENT;color:#fff;display:flex;align-items:center;
justify-content:center;font-weight:700;font-size:14px;flex:none}
.card h3{margin:0;font-size:17px} .card .meta{color:#6b7280;font-size:12px}
.line{font-size:12px;color:#374151;margin:8px 0 6px}
.chips{display:flex;gap:10px;flex-wrap:wrap;font-size:11px;color:#6b7280;margin-bottom:8px}
.chip{display:inline-block;min-width:24px;text-align:center;font-weight:700;font-size:12px;padding:2px 4px;border-radius:3px;margin-left:3px}
.chip.na{background:#f4f4f2;color:#9ca3af}
.card ul{margin:0 0 10px;padding-left:17px;font-size:12px;line-height:1.42;color:#1f2937} .card li{margin-bottom:3px}
.links{margin-top:auto;display:flex;gap:8px}
.links a{font-size:12px;text-decoration:none;color:ACCENT;border:1px solid #c9d2de;border-radius:14px;padding:4px 11px;background:#fff}
.links a.primary{background:ACCENT;color:#fff;border-color:ACCENT}
.method{margin-top:26px;font-size:12px;color:#4b5563;line-height:1.55;background:#fff;border:1px solid #dfe3e8;border-radius:6px;padding:12px 15px}
.method b{color:#1b1f24}
""".replace("ACCENT", ACCENT)


def _card(m: dict[str, Any], href_base: str = "") -> str:
    chips = "".join(f"<span>{esc(lab)}{grade_chip(g)}</span>" for lab, g in m["grades"])
    bullets = "".join(f"<li>{b}</li>" for b in m["bullets"][:3])
    pdf = (f'<a href="{esc(href_base + m["slug"] + ".pdf")}">PDF</a>' if m.get("pdf") else "")
    meta = " · ".join(x for x in (m.get("team"), m.get("hand"), {"SP": "Starter", "RP": "Reliever"}.get(m.get("role"), "")) if x)
    return (f'<div class="card"><div class="hd"><div class="badge">{esc(R.initials(m["name"]))}</div><div>'
            f'<h3>{esc(m["name"])}</h3><div class="meta">{esc(meta)}</div></div></div>'
            f'<div class="line">{esc(m["line"])}</div><div class="chips">{chips}</div><ul>{bullets}</ul>'
            f'<div class="links"><a class="primary" href="{esc(href_base + m["slug"] + ".html")}">View report</a>{pdf}</div></div>')


def write_index(out_dir: Path | str, entries: list[dict[str, Any]], *, title: str, kicker: str, lede: str,
                nav_html: str = "", head_extra: str = "") -> Path:
    """Gallery index (pitchers then hitters) linking each report's HTML and PDF."""
    out = Path(out_dir)
    sections = []
    for kind, label in (("pitcher", "Pitchers"), ("batter", "Hitters")):
        cards = [_card(m) for m in entries if m["kind"] == kind]
        if cards:
            sections.append(f"<h2>{label}</h2><div class='grid'>{''.join(cards)}</div>")
    through = max((m.get("through") or "" for m in entries), default="")
    method = ("<b>How these are built.</b> Every number comes from 2026 regular-season Statcast pitches (data through "
              f"{esc(through)}) plus FanGraphs season lines. Grades are league percentiles mapped to the 20–80 scale "
              "(50 = average, 10 points = 1 SD) within qualified pools; Stuff is a pitch-shape model of expected "
              "count-neutral run value. The bottom-line bullets are generated by a rules library that ranks findings "
              "by notability — each sentence is a template filled with the computed number it cites. Count plans, "
              "attack plans and usage suggestions come from this repo's situational, location and arsenal models; "
              "their effects are small and are presented as direction, not prescription.")
    lede_html = f'<div class="lede">{lede}</div>' if lede else ""
    html = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{esc(title)}</title>'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><style>{INDEX_CSS}</style>{head_extra}</head>'
            f'<body>{nav_html}<div class="wrap"><div class="top"><div class="kicker">{esc(kicker)}</div><h1>{esc(title)}</h1>'
            f'{lede_html}</div>{"".join(sections)}<div class="method">{method}</div>'
            f'<div style="color:#9ca3af;font-size:11px;margin-top:10px">Generated by pitch-dataset on {date.today().isoformat()}.</div>'
            f'</div></body></html>')
    path = out / "index.html"
    path.write_text(html, encoding="utf-8")
    return path


def load_entries(out_dir: Path | str) -> list[dict[str, Any]]:
    out = []
    for p in sorted(Path(out_dir).glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out
