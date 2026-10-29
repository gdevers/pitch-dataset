"""select-web integration: ``/reports`` search page + on-demand report generation endpoints."""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any

from pitch_dataset.reports.build import ReportService, player_index
from pitch_dataset.reports.render import slugify
from pitch_dataset.reports.svg import ACCENT

log = logging.getLogger(__name__)


def _nav_html(nav: list[tuple[str, str]], active: str) -> str:
    links = "".join(
        f'<a href="{href}"{" class=\"active\"" if href == active else ""}>{html.escape(label)}</a>' for href, label in nav
    )
    return f'<nav class="site-nav">{links}</nav>'


def register_report_routes(app: Any, service: ReportService, *, nav: list[tuple[str, str]],
                           out_dir: Path | str = "reports/players") -> None:
    """Add ``/reports``, ``/reports/view|pdf/{kind}/{id}`` and ``/api/reports/*`` to a FastAPI app."""
    from fastapi import HTTPException, Query
    from fastapi.responses import FileResponse, HTMLResponse

    out = Path(out_dir)
    index_cache: dict[str, Any] = {}

    def index():
        if "df" not in index_cache:
            index_cache["df"] = player_index(service.ctx)
        return index_cache["df"]

    def need(kind: str, pid: int) -> dict[str, Any]:
        if kind not in ("pitcher", "batter"):
            raise HTTPException(status_code=400, detail="kind must be 'pitcher' or 'batter'")
        df = index()
        row = df[(df["kind"] == kind) & (df["id"] == pid)]
        if row.empty:
            raise HTTPException(status_code=404, detail=f"No {kind} with id {pid} in {service.season}")
        if not bool(row["eligible"].iloc[0]):
            raise HTTPException(status_code=422, detail="Below the minimum sample (300 pitches) for a report")
        return row.iloc[0].to_dict()

    def ensure(kind: str, pid: int, *, pdf: bool, refresh: bool = False) -> tuple[Path, Path | None]:
        info = need(kind, pid)
        slug = slugify(info["name"])
        h, p = out / f"{slug}.html", out / f"{slug}.pdf"
        if refresh or not h.exists() or (pdf and not p.exists()):
            try:
                service.generate(kind, pid, out, pdf=pdf, screen_links=[("/reports", "← Player reports"),
                                                                        (f"/reports/pdf/{kind}/{pid}", "Download PDF")])
            except Exception as exc:
                log.exception("Report generation failed")
                raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}") from exc
        return h, (p if p.exists() else None)

    @app.get("/reports")
    def reports_page() -> HTMLResponse:
        return HTMLResponse(_PAGE.replace("{{NAV}}", _nav_html(nav, "/reports")).replace("ACCENT", ACCENT))

    @app.get("/api/reports/players")
    def api_report_players(q: str | None = None, kind: str | None = Query(None, pattern="^(pitcher|batter)$"),
                           limit: int = Query(60, ge=1, le=2000), eligible_only: bool = True) -> list[dict[str, Any]]:
        df = index()
        if kind:
            df = df[df["kind"] == kind]
        if eligible_only:
            df = df[df["eligible"]]
        if q:
            from pitch_dataset.reports.build import _fold

            fq = _fold(q)
            df = df[df["name"].map(_fold).str.contains(fq, regex=False) | df["team"].str.lower().eq(fq)]
        df = df.sort_values("n", ascending=False).head(limit)
        rows = []
        for r in df.to_dict("records"):
            slug = slugify(r["name"])
            rows.append({**{k: r[k] for k in ("kind", "id", "name", "team", "n", "hand", "qualified")},
                         "g1": r["g1"], "g2": r["g2"], "cached": (out / f"{slug}.html").exists()})
        return rows

    @app.post("/api/reports/generate")
    def api_report_generate(kind: str, id: int, pdf: bool = True) -> dict[str, Any]:
        h, p = ensure(kind, id, pdf=pdf, refresh=True)
        return {"kind": kind, "id": id, "html_url": f"/reports/view/{kind}/{id}",
                "pdf_url": f"/reports/pdf/{kind}/{id}" if p else None, "file": str(h)}

    @app.get("/reports/view/{kind}/{pid}")
    def report_view(kind: str, pid: int, refresh: bool = False) -> HTMLResponse:
        h, _ = ensure(kind, pid, pdf=False, refresh=refresh)
        return HTMLResponse(h.read_text(encoding="utf-8"))

    @app.get("/reports/pdf/{kind}/{pid}")
    def report_pdf(kind: str, pid: int) -> FileResponse:
        _, p = ensure(kind, pid, pdf=True)
        if p is None:
            raise HTTPException(status_code=503, detail="PDF export unavailable (Chrome not found)")
        return FileResponse(p, media_type="application/pdf", filename=p.name)


_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Player evaluation reports</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>
*{box-sizing:border-box} body{margin:0;font-family:"Inter","Helvetica Neue",Helvetica,Arial,sans-serif;color:#1b1f24;background:#f3f4f6;
font-variant-numeric:tabular-nums} .wrap{max-width:1080px;margin:0 auto;padding:18px 22px 40px}
.site-nav{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 14px;font-size:13px}
.site-nav a{color:ACCENT;text-decoration:none;padding:4px 10px;border:1px solid #d5dbe3;border-radius:14px;background:#fff}
.site-nav a.active{background:ACCENT;color:#fff;border-color:ACCENT}
h1{margin:0 0 4px;font-size:24px} .lede{color:#4b5563;font-size:13.5px;margin:0 0 14px;max-width:820px;line-height:1.5}
.bar{display:flex;gap:8px;align-items:center;margin-bottom:10px} input{flex:1;font:inherit;font-size:14px;padding:8px 11px;
border:1px solid #cfd6df;border-radius:6px} .seg button{font:inherit;font-size:13px;padding:7px 12px;border:1px solid #cfd6df;
background:#fff;cursor:pointer} .seg button:first-child{border-radius:6px 0 0 6px} .seg button:last-child{border-radius:0 6px 6px 0;border-left:0}
.seg button.on{background:ACCENT;color:#fff;border-color:ACCENT}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #dfe3e8;border-radius:6px;font-size:13px}
th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;text-align:left;padding:8px 10px;border-bottom:1px solid #dfe3e8}
td{padding:7px 10px;border-bottom:1px solid #f0f2f4} td.n{text-align:right;color:#4b5563}
.chip{display:inline-block;min-width:26px;text-align:center;font-weight:700;font-size:12px;padding:2px 4px;border-radius:3px;background:#eeeeec}
a.btn{font-size:12px;text-decoration:none;color:ACCENT;border:1px solid #c9d2de;border-radius:14px;padding:3px 10px;background:#fff;margin-right:4px}
a.btn.primary{background:ACCENT;color:#fff;border-color:ACCENT} .muted{color:#6b7280} #status{font-size:12px;color:#6b7280;margin:6px 0}
</style></head><body><div class="wrap">{{NAV}}
<h1>Player evaluation reports</h1>
<p class="lede">Two-page, print-ready pitcher and hitter evaluations generated on demand from the season's Statcast data, FanGraphs
lines and this repo's models (first view of a player takes a few seconds; PDFs via headless Chrome). Also available as
<code>uv run pitch-dataset report --pitcher "Name"</code> / <code>--batter</code> / <code>--team SDP</code>.</p>
<div class="bar"><div class="seg"><button data-k="pitcher" class="on">Pitchers</button><button data-k="batter">Hitters</button></div>
<input id="q" placeholder="Search by name or team (e.g. Skubal, SDP)…" autocomplete="off"></div>
<div id="status"></div>
<table><thead><tr><th>Player</th><th>Team</th><th>Hand</th><th style="text-align:right">Pitches</th><th id="g1h">Stuff</th>
<th id="g2h">Cmd</th><th></th></tr></thead><tbody id="rows"></tbody></table></div>
<script>
let kind = "pitcher", timer = null;
const $ = s => document.querySelector(s);
function chipColor(g){ if(g==null) return "#f4f4f2"; const t=Math.max(-1,Math.min(1,(g-50)/25));
  return t>=0 ? `rgba(192,57,43,${0.15+0.7*t})` : `rgba(44,93,156,${0.15+0.7*-t})`; }
function chip(g){ const c=chipColor(g); const dark=g!=null && Math.abs(g-50)>=15;
  return `<span class="chip" style="background:${c};color:${dark?'#fff':'#1b1f24'}">${g==null?'–':g}</span>`; }
async function load(){
  const q = $("#q").value.trim();
  $("#g1h").textContent = kind==="pitcher" ? "Stuff" : "Hit"; $("#g2h").textContent = kind==="pitcher" ? "Cmd" : "Power";
  $("#status").textContent = "Loading…";
  const r = await fetch(`/api/reports/players?kind=${kind}&limit=80` + (q ? `&q=${encodeURIComponent(q)}` : ""));
  if(!r.ok){ $("#status").textContent = "Error: " + (await r.text()); return; }
  const rows = await r.json();
  $("#status").textContent = `${rows.length} ${kind==="pitcher"?"pitchers":"hitters"} with ≥300 pitches` + (q?` matching “${q}”`:" (most pitches first)");
  $("#rows").innerHTML = rows.map(p => `<tr><td><b>${p.name}</b>${p.qualified?'':' <span class="muted">(small sample)</span>'}</td>
    <td>${p.team||''}</td><td>${p.hand}</td><td class="n">${p.n.toLocaleString()}</td><td>${chip(p.g1)}</td><td>${chip(p.g2)}</td>
    <td><a class="btn primary" target="_blank" href="/reports/view/${p.kind}/${p.id}">${p.cached?'View':'Generate'} report</a>
    <a class="btn" href="/reports/pdf/${p.kind}/${p.id}">PDF</a></td></tr>`).join("");
}
document.querySelectorAll(".seg button").forEach(b => b.onclick = () => {
  document.querySelectorAll(".seg button").forEach(x => x.classList.remove("on")); b.classList.add("on"); kind = b.dataset.k; load(); });
$("#q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 200); });
load();
</script></body></html>"""
