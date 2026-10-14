"""Page shell, print CSS, shared HTML components, and PDF export (headless Chrome)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from pitch_dataset.reports.svg import ACCENT, div_color, esc, grade_chip, pct_bar

log = logging.getLogger(__name__)

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "chromium", "chromium-browser",
]

CSS = """
@page { size: 8.5in 11in; margin: 0; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; background: #e6e8eb; color: #1b1f24;
  font-family: "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 7.6pt; line-height: 1.28;
  font-variant-numeric: tabular-nums; }
.page { width: 8.5in; height: 11in; margin: 0.25in auto; background: #fff; position: relative; overflow: hidden;
  padding: 0.34in 0.4in 0.3in; display: flex; flex-direction: column; box-shadow: 0 2px 10px rgba(0,0,0,.18); }
@media print { body { background: none; } .page { margin: 0; box-shadow: none; break-after: page; }
  .page:last-child { break-after: auto; } .screen-bar { display: none !important; } }
.screen-bar { max-width: 8.5in; margin: 14px auto -6px; display: flex; gap: 10px; align-items: center;
  font-size: 12px; font-family: inherit; }
.screen-bar a { color: ACCENT; text-decoration: none; border: 1px solid #c9d2de; background: #fff;
  padding: 4px 10px; border-radius: 14px; }
.screen-bar .sp { flex: 1; }
.rhead { display: flex; align-items: flex-end; gap: 10px; border-bottom: 2.2px solid ACCENT; padding-bottom: 5px; }
.badge { width: 40px; height: 40px; border-radius: 50%; background: ACCENT; color: #fff; display: flex;
  align-items: center; justify-content: center; font-weight: 700; font-size: 14pt; letter-spacing: .5px; flex: none; }
.who { flex: 1; min-width: 0; }
.kicker { font-size: 6.6pt; letter-spacing: .12em; text-transform: uppercase; color: ACCENT; font-weight: 700; }
.who h1 { margin: 1px 0 0; font-size: 17pt; line-height: 1.05; letter-spacing: -.01em; }
.who .meta { color: #4b5563; font-size: 8pt; margin-top: 2px; }
.rmeta { text-align: right; font-size: 6.8pt; color: #4b5563; line-height: 1.35; }
.rmeta b { color: #1b1f24; }
.compact .who h1 { font-size: 12.5pt; } .compact .badge { width: 28px; height: 28px; font-size: 10pt; }
.statline { display: grid; gap: 0; margin-top: 6px; border: 1px solid #dfe3e8; border-radius: 3px; }
.statline .c { padding: 3px 5px 3px; border-right: 1px solid #eef0f3; min-width: 0; }
.statline .c:last-child { border-right: 0; }
.statline .l { font-size: 5.9pt; text-transform: uppercase; letter-spacing: .06em; color: #6b7280; white-space: nowrap; }
.statline .v { font-size: 10.5pt; font-weight: 700; line-height: 1.15; white-space: nowrap; }
.pbar { display: inline-block; position: relative; width: 100%; height: 3px; background: #eceef1; border-radius: 2px;
  vertical-align: middle; }
.pfill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 2px; opacity: .55; }
.pdot { position: absolute; top: -2px; width: 7px; height: 7px; margin-left: -3.5px; border-radius: 50%;
  border: 1px solid #fff; }
.pv { display: none; }
.pbar.na { background: repeating-linear-gradient(90deg,#eceef1 0 3px,#fff 3px 5px); }
.row { display: flex; gap: 12px; margin-top: 7px; min-height: 0; }
.col { min-width: 0; display: flex; flex-direction: column; }
.sec { margin-top: 7px; }
h2 { font-size: 8.4pt; margin: 0 0 1px; line-height: 1.2; }
h2 .tag { font-size: 6.2pt; font-weight: 700; color: #fff; background: ACCENT; padding: 1px 4px; border-radius: 2px;
  margin-right: 5px; letter-spacing: .06em; text-transform: uppercase; vertical-align: 1px; }
.sub { color: #6b7280; font-size: 6.5pt; margin-bottom: 3px; }
.bl { background: #f4f6f9; border-left: 3.5px solid ACCENT; padding: 6px 9px 6px 8px; }
.bl h3 { margin: 0 0 3px; font-size: 7pt; letter-spacing: .12em; text-transform: uppercase; color: ACCENT; }
.bl ol { margin: 0; padding-left: 14px; }
.bl li { margin: 0 0 3px; font-size: 7.9pt; line-height: 1.32; }
.bl li:last-child { margin-bottom: 0; }
.bl li b { font-weight: 700; }
.grades { border: 1px solid #dfe3e8; padding: 5px 7px; }
.grades h3 { margin: 0 0 3px; font-size: 7pt; letter-spacing: .12em; text-transform: uppercase; color: ACCENT;
  display: flex; justify-content: space-between; }
.grades h3 span { color: #6b7280; letter-spacing: 0; text-transform: none; font-weight: 400; font-size: 6.2pt; }
.gr { display: grid; grid-template-columns: 74px 26px 1fr 54px; align-items: center; gap: 6px; padding: 2px 0;
  border-bottom: 1px solid #f0f2f4; }
.gr:last-child { border-bottom: 0; }
.gr .gl { font-weight: 600; }
.gr .gn { color: #6b7280; font-size: 6.3pt; text-align: right; white-space: nowrap; }
.chip { display: inline-block; min-width: 21px; text-align: center; font-weight: 700; font-size: 7.4pt; padding: 1px 3px;
  border-radius: 3px; line-height: 1.25; }
.chip.big { min-width: 26px; font-size: 9pt; padding: 2px 4px; }
.chip.na { background: #f4f4f2; color: #9ca3af; }
table.tbl { border-collapse: collapse; width: 100%; font-size: 7pt; }
.tbl th { font-size: 5.9pt; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; font-weight: 600;
  text-align: right; padding: 2px 3px; border-bottom: 1px solid #c9ced6; white-space: nowrap; }
.tbl th.l, .tbl td.l { text-align: left; }
.tbl td { text-align: right; padding: 1.6px 3px; border-bottom: 1px solid #f0f2f4; white-space: nowrap; }
.tbl td.c, .tbl th.c { text-align: center; }
.tbl tr.small td { color: #9ca3af; }
.tbl .grp th { border-bottom: 0; padding-bottom: 0; text-align: center; color: ACCENT; }
.tbl td.sep, .tbl th.sep { border-left: 1px solid #e3e6ea; }
.sw { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 4px; vertical-align: 0; }
.legend { color: #6b7280; font-size: 6.3pt; margin-top: 2px; }
.legend .sc { display: inline-block; width: 52px; height: 6px; vertical-align: 0;
  background: linear-gradient(90deg, #2c5d9c, #eeeeec, #c0392b); margin: 0 3px; }
.legend .sq { display: inline-block; width: 52px; height: 6px; vertical-align: 0;
  background: linear-gradient(90deg, #fafbfc, ACCENT); margin: 0 3px; }
.foot { margin-top: auto; padding-top: 5px; border-top: 1px solid #d5dae1; display: flex; justify-content: space-between;
  gap: 12px; color: #6b7280; font-size: 6.1pt; line-height: 1.3; }
.foot .notes { flex: 1; }
.foot .pg { white-space: nowrap; font-weight: 700; color: #1b1f24; }
.method { font-size: 6.1pt; color: #4b5563; line-height: 1.32; border-top: 1px solid #e3e6ea; padding-top: 4px; margin-top: 6px; }
.method b { color: #1b1f24; }
.kv { display: grid; grid-template-columns: auto 1fr; gap: 1px 8px; font-size: 7pt; }
.kv .k { color: #6b7280; }
.note { font-size: 7.1pt; line-height: 1.32; margin: 0 0 3px; }
.note b { font-weight: 700; }
.flag { color: #b7791f; font-weight: 700; }
.muted { color: #6b7280; }
.comp { display: grid; grid-template-columns: 1fr 70px; gap: 1px 6px; align-items: center; padding: 2px 0;
  border-bottom: 1px solid #f0f2f4; }
.comp .nm { font-weight: 600; }
.comp .d { color: #6b7280; font-size: 6.4pt; grid-column: 1 / 3; }
.simbar { height: 5px; background: #eceef1; border-radius: 3px; position: relative; }
.simbar span { position: absolute; left: 0; top: 0; bottom: 0; background: ACCENT; border-radius: 3px; }
.svgwrap svg { display: block; }
.mini-grid { display: grid; gap: 2px 4px; }
.mini-grid .hd { font-size: 6pt; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; text-align: center; }
""".replace("ACCENT", ACCENT)


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def initials(name: str) -> str:
    parts = [p for p in re.split(r"[\s.]+", name) if p and p.lower() not in {"jr", "sr", "ii", "iii"}]
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else name[:2].upper()


def tint(p: float | None, strength: float = 0.62) -> str:
    """Lightened diverging color for table-cell backgrounds (p in 0..1, 1 = good)."""
    if p is None or not np.isfinite(p):
        return "transparent"
    c = div_color(p)
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    mix = [int(255 - (255 - v) * strength) for v in (r, g, b)]
    return "#" + "".join(f"{v:02x}" for v in mix)


def header(*, kind: str, name: str, meta: str, rmeta: str, compact: bool = False) -> str:
    return (
        f'<header class="rhead{" compact" if compact else ""}"><div class="badge">{esc(initials(name))}</div>'
        f'<div class="who"><div class="kicker">{esc(kind)}</div><h1>{esc(name)}</h1>'
        f'{"" if compact else f"<div class=meta>{meta}</div>"}</div><div class="rmeta">{rmeta}</div></header>'
    )


def statline(cells: list[tuple[str, str, float | None]], widths: list[float] | None = None) -> str:
    """cells: (label, value, percentile 0–100 or None); optional relative column widths."""
    inner = "".join(
        f'<div class="c"><div class="l">{esc(lab)}</div><div class="v">{val}</div>{pct_bar(p, label=False)}</div>'
        for lab, val, p in cells
    )
    cols = " ".join(f"{w}fr" for w in widths) if widths else f"repeat({len(cells)},1fr)"
    return f'<div class="statline" style="grid-template-columns:{cols}">{inner}</div>'


def grades_panel(title: str, rows: list[tuple[str, float | None, float | None, str]], note: str = "",
                 extra: str = "") -> str:
    """rows: (label, grade, percentile 0–100, right-side note); ``extra`` = raw HTML appended inside the panel."""
    body = "".join(
        f'<div class="gr"><span class="gl">{esc(lab)}</span>{grade_chip(g, big=True)}{pct_bar(p, label=False)}'
        f'<span class="gn">{n}</span></div>'
        for lab, g, p, n in rows
    )
    return f'<div class="grades"><h3>{esc(title)}<span>{note}</span></h3>{body}{extra}</div>'


def bottom_line(bullets: list[str]) -> str:
    items = "".join(f"<li>{b}</li>" for b in bullets)
    return f'<div class="bl"><h3>Bottom line</h3><ol>{items}</ol></div>'


def section(title: str, sub: str, body: str, *, tag: str = "", cls: str = "sec", style: str = "") -> str:
    t = f'<span class="tag">{esc(tag)}</span>' if tag else ""
    return f'<section class="{cls}" style="{style}"><h2>{t}{title}</h2><div class="sub">{sub}</div>{body}</section>'


def footer(*, kind: str, through: str, page: int, pages: int, notes: str) -> str:
    return (
        f'<footer class="foot"><div class="notes"><b>{esc(kind)}</b> · Data through {esc(through)} (regular season) · '
        f'Generated by pitch-dataset on {date.today().isoformat()} · {notes}</div>'
        f'<div class="pg">Page {page} / {pages}</div></footer>'
    )


def document(title: str, pages: list[str], *, screen_links: list[tuple[str, str]] | None = None) -> str:
    bar = ""
    if screen_links:
        links = "".join(f'<a href="{esc(h)}">{esc(t)}</a>' for h, t in screen_links)
        bar = f'<div class="screen-bar">{links}<span class="sp"></span><span class="muted">Letter · 2 pages · print-ready</span></div>'
    body = "".join(f'<div class="page">{p}</div>' for p in pages)
    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{esc(title)}</title>'
        f'<meta name="viewport" content="width=device-width, initial-scale=1"><style>{CSS}</style></head>'
        f"<body>{bar}{body}</body></html>"
    )


def find_chrome() -> str | None:
    for cand in CHROME_CANDIDATES:
        if Path(cand).exists():
            return cand
        found = shutil.which(cand)
        if found:
            return found
    return None


def html_to_pdf(html_path: Path | str, pdf_path: Path | str, *, timeout: float = 90) -> Path | None:
    """Print an HTML file to PDF with headless Chrome (CSS ``@page`` controls size/margins)."""
    chrome = find_chrome()
    if chrome is None:
        log.warning("Chrome not found; skipping PDF for %s", html_path)
        return None
    html_path, pdf_path = Path(html_path).resolve(), Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="report-chrome-") as profile:
        cmd = [
            chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            f"--user-data-dir={profile}", "--no-pdf-header-footer", "--hide-scrollbars",
            "--virtual-time-budget=4000", f"--print-to-pdf={pdf_path}", html_path.as_uri(),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.SubprocessError, OSError) as exc:
            log.warning("PDF export failed for %s: %s", html_path, exc)
            return None
    return pdf_path if pdf_path.exists() else None


def fmt_date(d: Any) -> str:
    try:
        return f"{d:%b} {d.day}"
    except (TypeError, ValueError):
        return str(d)


def method_block(items: list[tuple[str, str]]) -> str:
    return '<div class="method">' + " ".join(f"<b>{esc(k)}.</b> {v}" for k, v in items) + "</div>"


def color_legend() -> str:
    return ('<span class="legend">Color: <span class="sc"></span> blue = poor · grey = average · red = good '
            '(from this player\'s perspective)</span>')


def pct_cell(text: str, p: float | None) -> str:
    """Table cell tinted by a 0–100 percentile (100 = good for the subject)."""
    bg = tint(None if p is None or not np.isfinite(p) else p / 100.0)
    return f'<td style="background:{bg}">{text}</td>'


def kv_list(items: list[tuple[str, str]]) -> str:
    return '<div class="kv">' + "".join(f'<span class="k">{esc(k)}</span><span>{v}</span>' for k, v in items) + "</div>"

