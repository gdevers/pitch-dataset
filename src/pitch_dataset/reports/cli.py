"""``pitch-dataset report``: player evaluation reports (HTML + PDF), team batches, portfolio gallery."""

from __future__ import annotations

import argparse
import logging
import os
import re
from pathlib import Path

from pitch_dataset.reports.build import (
    MIN_REPORT_PITCHES,
    ReportService,
    resolve_player,
    team_roster,
    write_index,
)

log = logging.getLogger(__name__)

PORTFOLIO_PITCHERS = ["Dylan Cease", "Tarik Skubal", "Paul Skenes", "Kevin Gausman", "Logan Webb", "Chase Burns"]
PORTFOLIO_HITTERS = ["Rafael Devers", "Aaron Judge", "Kyle Schwarber", "Isaac Paredes", "Luis Arráez", "Juan Soto"]
PORTFOLIO_DIR = Path("docs/reports")


def add_report_parser(sub: argparse._SubParsersAction) -> None:
    rep = sub.add_parser(
        "report",
        help="Generate 2-page pitcher / hitter evaluation reports (HTML + PDF)",
        description=(
            "Advance-scouting style evaluation reports built from the season's Statcast pitches, FanGraphs lines "
            "and this repo's models. Examples: report --pitcher 'Dylan Cease'; report --batter 'Rafael Devers'; "
            "report --team SDP; report --portfolio."
        ),
    )
    rep.add_argument("--pitcher", action="append", default=[], help="Pitcher name or MLBAM id (repeatable)")
    rep.add_argument("--batter", action="append", default=[], help="Batter name or MLBAM id (repeatable)")
    rep.add_argument("--team", help="Team abbreviation (FanGraphs or MLB, e.g. SDP / SD): active-roster batch + index")
    rep.add_argument("--portfolio", action="store_true", help=f"Rebuild the GitHub Pages gallery in {PORTFOLIO_DIR}/")
    rep.add_argument("--season", type=int, default=2026)
    rep.add_argument("--data-dir", default="data")
    rep.add_argument("--models-dir", default="models")
    rep.add_argument("--out", help="Output directory (default reports/players, reports/teams/<TEAM>, or docs/reports)")
    rep.add_argument("--no-pdf", action="store_true", help="Skip PDF export (HTML only)")


def cmd_report(args: argparse.Namespace) -> int:
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 4))
    svc = ReportService(data_dir=Path(args.data_dir), models_dir=args.models_dir, season=args.season)
    if not (args.pitcher or args.batter or args.team or args.portfolio):
        log.error("Nothing to do: pass --pitcher, --batter, --team, or --portfolio")
        return 2
    pdf = not args.no_pdf
    status = 0
    if args.pitcher or args.batter:
        out = Path(args.out or "reports/players")
        for kind, queries in (("pitcher", args.pitcher), ("batter", args.batter)):
            for q in queries:
                try:
                    pid = resolve_player(svc.ctx, q, kind)
                    m = svc.generate(kind, pid, out, pdf=pdf)
                except (LookupError, ValueError) as exc:
                    log.error("%s", exc)
                    status = 1
                    continue
                print(f"{m['name']}: {m['html']}" + (f"  ·  {m['pdf']}" if m["pdf"] else ""))
                for b in m["bullets"]:
                    print("   -", re.sub(r"<[^>]+>", "", b))
    if args.team:
        status |= _team(svc, args.team, Path(args.out or f"reports/teams/{args.team.upper()}"), pdf)
    if args.portfolio:
        status |= build_portfolio(svc, Path(args.out or PORTFOLIO_DIR), pdf=pdf)
    return status


def _team(svc: ReportService, team: str, out: Path, pdf: bool) -> int:
    try:
        roster = team_roster(svc.ctx, team)
    except (LookupError, FileNotFoundError) as exc:
        log.error("%s", exc)
        return 1
    entries = []
    for kind in ("pitcher", "batter"):
        for pid in roster[kind]:
            try:
                entries.append(svc.generate(kind, pid, out, pdf=pdf, screen_links=[("index.html", "← Team index")]))
                log.info("%s report: %s", kind, entries[-1]["name"])
            except Exception:
                log.exception("Report failed for %s %s", kind, pid)
    idx = write_index(out, entries, title=f"{team.upper()} — player evaluations", kicker=f"{svc.season} team batch",
                      lede=f"{len(entries)} active-roster players with at least {MIN_REPORT_PITCHES} pitches thrown or seen.")
    print(f"{len(entries)} reports → {idx}")
    return 0


def build_portfolio(svc: ReportService, out: Path, *, pdf: bool = True) -> int:
    """Regenerate the docs/reports gallery as a standalone share surface (no portfolio-site nav)."""
    if out.exists():
        for p in out.glob("*"):
            if p.suffix in {".html", ".pdf", ".json"}:
                p.unlink()
    out.mkdir(parents=True, exist_ok=True)
    # Stay inside the reports gallery only — no links out to the rest of the portfolio.
    links = [("index.html", "← All player reports")]
    entries, status = [], 0
    for kind, names in (("pitcher", PORTFOLIO_PITCHERS), ("batter", PORTFOLIO_HITTERS)):
        for name in names:
            try:
                pid = resolve_player(svc.ctx, name, kind)
                m = svc.generate(kind, pid, out, pdf=pdf, screen_links=links)
            except Exception:
                log.exception("Portfolio report failed for %s", name)
                status = 1
                continue
            m["html"], m["pdf"] = Path(m["html"]).name, Path(m["pdf"]).name if m["pdf"] else None
            entries.append(m)
    for p in out.glob("*.json"):
        p.unlink()
    write_index(out, entries, title="Player evaluation reports", kicker="pitch-dataset", lede="")
    print(f"Portfolio: {len(entries)} reports → {out / 'index.html'}")
    return status
