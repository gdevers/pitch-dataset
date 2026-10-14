"""Two-page hitter evaluation report: data assembly + HTML rendering."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from pitch_dataset.location import assign_location_zones, zone_label
from pitch_dataset.reports import narrative
from pitch_dataset.reports import render as R
from pitch_dataset.reports import svg as S
from pitch_dataset.reports.context import (
    FAMILY_GROUP,
    PITCH_FAMILY,
    PITCH_NAMES,
    LeagueContext,
    band_stats,
    current_team,
    il_stints,
    pitch_bands,
    player_pitches,
)
from pitch_dataset.reports.defense import describe_moves, recommend_alignment
from pitch_dataset.reports.models import BUCKETS, COUNTS, hitter_attack_plan

log = logging.getLogger(__name__)

GROUP_NAMES = {"FB": "Fastballs", "BRK": "Breaking", "OFF": "Offspeed"}
ROLL_GAMES = 15
TREND_SPECS = [  # key, label, threshold for a flag, formatter
    ("xwoba", "xwOBA", 0.045, S.rate3),
    ("ev", "Avg exit velo", 2.0, lambda v: f"{v:.1f} mph"),
    ("chase", "Chase rate", 0.05, lambda v: f"{v * 100:.0f}%"),
]


def _ok(v: Any) -> bool:
    return v is not None and np.isfinite(v)


# ------------------------------------------------------------------ data


def _with_zones(df: pd.DataFrame) -> pd.DataFrame:
    z = assign_location_zones(df["plate_x"], df["plate_z"], df["stand"], df["sz_top"], df["sz_bot"])["loc_zone"]
    return df.assign(loc_zone=z.to_numpy())


def _zone_maps(df: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    maps = {}
    for hand in ("R", "L"):
        for grp in ("FB", "BRK", "OFF"):
            g = df[(df["p_throws"] == hand) & (df["grp"] == grp) & df["loc_zone"].notna()]
            stand = str(g["stand"].mode().iloc[0]) if len(g) else "R"
            g = g[g["stand"] == stand]
            by = g.groupby("loc_zone")
            sw = by["swing"].sum()
            maps[(hand, grp)] = {
                "stand": stand, "n": len(g),
                "swing": by["swing"].mean().to_dict(), "n_all": by.size().to_dict(),
                "whiff": (by["whiff"].sum() / sw.where(sw > 0)).to_dict(), "n_sw": sw.to_dict(),
                "xwcon": by["xwoba_con"].mean().to_dict(), "n_bip": by["bip"].sum().to_dict(),
            }
    return maps


def _perf_bands(ctx: LeagueContext, df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for label, mask in pitch_bands(df).items():
        s = band_stats(df, mask)
        lg = ctx.bands.get(label, {})
        out.append({"label": label, **s, "swings": float(df.loc[mask, "swing"].sum()),
                    **{f"lg_{k}": v for k, v in lg.items()}})
    return out


def _count_tendencies(ctx: LeagueContext, df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("count")
    oz = (~df["in_zone"]).groupby(df["count"]).sum()
    sw = g["swing"].sum()
    t = pd.DataFrame({
        "n": g.size(), "swing": g["swing"].mean(), "chase": g["o_swing"].sum() / oz.where(oz > 0),
        "whiff": g["whiff"].sum() / sw.where(sw > 0), "xwcon": g["xwoba_con"].mean(), "bip": g["bip"].sum(),
    }).reindex(COUNTS)
    lg = ctx.counts.reindex(COUNTS)
    for c in ("swing", "chase", "whiff", "xwcon"):
        t[f"lg_{c}"] = lg[c]
    return t


def _spray(ctx: LeagueContext, df: pd.DataFrame, stand: str) -> dict[str, Any]:
    bip = df[df["bip"]].copy()
    ev = bip["events"].fillna("")
    bip["result"] = np.where(ev.eq("home_run"), "hr", np.where(ev.isin(["single", "double", "triple"]), "hit", "out"))
    L = ctx.league
    lg = {"pull": L["bip_pull"], "oppo": L["bip_oppo"], "center": 1 - L["bip_pull"] - L["bip_oppo"],
          "pull_air": L["bip_pull_air"], "gb": L["bb_gb"], "ld": L["bb_ld"], "fb": L["bb_fb"], "pu": L["bb_pu"]}
    n = len(bip)
    bb = bip["bb_type"].value_counts(normalize=True)
    mix = {
        "n": n, "pull": bip["pull"].mean(), "oppo": bip["oppo"].mean(),
        "center": 1 - bip["pull"].mean() - bip["oppo"].mean(), "gb": bb.get("ground_ball", 0.0),
        "ld": bb.get("line_drive", 0.0), "fb": bb.get("fly_ball", 0.0), "pu": bb.get("popup", 0.0),
        "pull_air": bip["pull_air"].mean(), "lg": lg,
    }
    align = None
    try:
        align = recommend_alignment(bip[bip["stand"] == stand], stand)
    except Exception:
        log.exception("Alignment optimizer failed")
    return {"balls": bip[["x_ft", "y_ft", "result"]], "mix": mix, "align": align}


def _attack(ctx: LeagueContext, bid: int, models: dict[str, Any]) -> pd.DataFrame:
    from pitch_dataset.reports.context import _all_columns, read_regular_season
    from pitch_dataset.storage import pitch_path

    path = pitch_path(ctx.data_dir, season=ctx.season, league="mlb")
    raw = read_regular_season(path, columns=_all_columns(path), filters=[("batter", "==", int(bid))])
    try:
        return hitter_attack_plan(models, ctx.attack_pitchers, raw, data_dir=ctx.data_dir, season=ctx.season)
    except Exception:
        log.exception("Attack plan failed for %s", bid)
        return pd.DataFrame()


def _zone_support(df: pd.DataFrame, plan: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, Any]]:
    """His own results in each recommended (hand, pitch group, zone) cell."""
    out = {}
    if plan is None or plan.empty:
        return out
    for r in plan.itertuples():
        if not r.zone:
            continue
        grp = FAMILY_GROUP.get(PITCH_FAMILY.get(r.pitch_type, ""), "FB")
        g = df[(df["p_throws"] == r.hand) & (df["grp"] == grp) & (df["loc_zone"] == r.zone)]
        sw = g["swing"].sum()
        out[(r.hand, r.pitch_type, r.zone)] = {
            "n": len(g), "swing": g["swing"].mean() if len(g) else np.nan,
            "whiff": g["whiff"].sum() / sw if sw else np.nan,
            "xwcon": g["xwoba_con"].mean() if g["bip"].any() else np.nan, "grp_name": GROUP_NAMES[grp],
        }
    return out


def _trends(df: pd.DataFrame) -> dict[str, Any]:
    g = df.groupby("game_pk")
    games = pd.DataFrame({
        "date": g["game_date"].first(), "pa": g["pa_end"].sum(), "xw_sum": g["xwoba_pa"].sum(),
        "ev_sum": g["ev"].sum(), "ev_n": g["ev"].count(), "o_sw": g["o_swing"].sum(),
        "o_n": (~df["in_zone"]).groupby(df["game_pk"]).sum(),
    }).sort_values("date").reset_index(drop=True)
    roll = games[["pa", "xw_sum", "ev_sum", "ev_n", "o_sw", "o_n"]].rolling(ROLL_GAMES, min_periods=5).sum()
    games["xwoba"] = roll["xw_sum"] / roll["pa"].where(roll["pa"] > 0)
    games["ev"] = roll["ev_sum"] / roll["ev_n"].where(roll["ev_n"] > 0)
    games["chase"] = roll["o_sw"] / roll["o_n"].where(roll["o_n"] > 0)
    season = {
        "xwoba": games["xw_sum"].sum() / max(games["pa"].sum(), 1),
        "ev": games["ev_sum"].sum() / max(games["ev_n"].sum(), 1),
        "chase": games["o_sw"].sum() / max(games["o_n"].sum(), 1),
    }
    flags = []
    if len(games) >= 30:
        last = games.iloc[-1]
        for key, label, thr, fmt in TREND_SPECS:
            r, b = last[key], season[key]
            if _ok(r) and _ok(b) and abs(r - b) >= thr:
                flags.append({"key": key, "label": label, "delta": r - b, "z": (r - b) / thr,
                              "recent_txt": fmt(r), "base_txt": fmt(b), "since": games["date"].iloc[-ROLL_GAMES]})
    flags.sort(key=lambda f: -abs(f["z"]))
    return {"games": games, "season": season, "flags": flags}


def _splits(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    pa = df[df["pa_end"]]
    ev = pa["events"].fillna("")
    woba = pd.to_numeric(pa["woba_value"], errors="coerce")
    out = {}
    for hand in ("R", "L"):
        m = pa["p_throws"] == hand
        g = df[df["p_throws"] == hand]
        n = int(m.sum())
        ab = n - int(ev[m].isin(["walk", "intent_walk", "hit_by_pitch", "sac_fly", "sac_bunt", "catcher_interf"]).sum())
        hits = int(ev[m].isin(["single", "double", "triple", "home_run"]).sum())
        oz = (~g["in_zone"]).sum()
        bip = g["bip"].sum()
        out[f"vs {hand}HP"] = {
            "pa": n, "avg": hits / ab if ab else np.nan, "woba": woba[m].mean() if n else np.nan,
            "xwoba": pa.loc[m, "xwoba_pa"].mean() if n else np.nan,
            "k": ev[m].str.startswith("strikeout").mean() if n else np.nan,
            "bb": ev[m].isin(["walk", "intent_walk"]).mean() if n else np.nan, "hr": int(ev[m].eq("home_run").sum()),
            "barrel": g["barrel"].sum() / bip if bip else np.nan, "chase": g["o_swing"].sum() / oz if oz else np.nan,
        }
    return out


def _comps(ctx: LeagueContext, bid: int) -> list[dict[str, Any]]:
    bat = ctx.batters
    ids = bat.index[bat["qualified"]].tolist()
    if bid not in ids:
        ids.append(bid)
    cols = {"barrel_pct": 1.3, "ev90": 1.2, "contact_pct": 1.2, "chase_pct": 1.0, "z_swing_pct": 0.8,
            "pull_air_pct": 0.9, "gb_pct": 0.8, "la_mean": 0.6, "whiff_FB": 0.6, "whiff_BRK": 0.6, "whiff_OFF": 0.5,
            "BB%": 0.6, "K%": 0.6}
    f = bat.loc[ids, [c for c in cols if c in bat.columns]].astype(float)
    z = (f - f.mean()) / f.std().replace(0, 1)
    z = z.fillna(0) * pd.Series(cols)[f.columns]
    dist = np.sqrt(((z - z.loc[bid]) ** 2).sum(axis=1)).drop(bid)
    a = z.sample(min(200, len(z)), random_state=1).to_numpy()
    b = z.sample(min(200, len(z)), random_state=2).to_numpy()
    ref = float(np.median(np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2))))
    out = []
    for oid, d in dist.nsmallest(3).items():
        r = bat.loc[oid]
        team = current_team(ctx.data_dir, ctx.season, int(oid)) or str(r.get("fg_team") or "")
        out.append({
            "id": int(oid), "name": ctx.name(oid), "team": "" if team.startswith("-") else team,
            "sim": max(0.0, 1 - d / ref), "power": r.get("g_power"), "hit": r.get("g_hit"),
            "note": (f"{r['stand']}HB · {S.pct(r.get('barrel_pct'), 1)} barrel · EV90 {S.num(r.get('ev90'), 1)} · "
                     f"{S.pct(r.get('contact_pct'))} contact · {S.pct(r.get('chase_pct'))} chase · xwOBA {S.rate3(r.get('xwOBA'))}"),
        })
    return out


def _bats(df: pd.DataFrame) -> str:
    share = df.drop_duplicates(["game_pk", "at_bat_number"])["stand"].value_counts(normalize=True)
    if share.get("L", 0) >= 0.15 and share.get("R", 0) >= 0.15:
        return "S"
    return str(share.index[0]) if len(share) else "R"


def build_hitter_data(ctx: LeagueContext, bid: int, models: dict[str, Any]) -> dict[str, Any]:
    bat = ctx.batters
    if bid not in bat.index:
        raise ValueError(f"No {ctx.season} regular-season pitches seen by batter {bid}")
    row = bat.loc[bid]
    df = _with_zones(player_pitches(ctx, batter=bid))
    bats = _bats(df)
    stand = str(df["stand"].mode().iloc[0])
    plan = _attack(ctx, bid, models)
    spray = _spray(ctx, df, stand)
    data = {
        "kind": "hitter", "id": bid, "name": ctx.name(bid), "bats": bats, "stand": stand,
        "team": current_team(ctx.data_dir, ctx.season, bid) or str(row.get("fg_team") or ""),
        "age": row.get("fg_age") if _ok(row.get("fg_age")) else row.get("age"),
        "row": row, "df": df, "ctx": ctx, "stints": il_stints(ctx.data_dir, ctx.season, bid),
        "maps": _zone_maps(df), "perf": _perf_bands(ctx, df), "counts": _count_tendencies(ctx, df),
        "spray": spray, "align": spray["align"], "attack": plan, "zone_support": _zone_support(df, plan),
        "trend": _trends(df), "splits": _splits(df), "comps": _comps(ctx, bid),
    }
    data["findings"] = narrative.hitter_findings(data)
    return data


# ------------------------------------------------------------------ rendering


def _p(row: pd.Series, col: str) -> float | None:
    v = row.get(f"pct_{col}")
    return float(v) if _ok(v) else None


def _page1(d: dict[str, Any]) -> str:
    ctx: LeagueContext = d["ctx"]
    row = d["row"]
    age = f"Age {int(d['age'])}" if _ok(d.get("age")) else ""
    bats = {"L": "Bats L", "R": "Bats R", "S": "Switch hitter"}[d["bats"]]
    meta = " · ".join(x for x in [d["team"], bats, age, f"{int(row['n']):,} pitches seen", f"{int(row['games'])} G"] if x)
    rmeta = (f"<b>Hitter evaluation</b><br>{ctx.season} regular season<br>Data through <b>{ctx.date_range[1]}</b>"
             f"<br>MLBAM {d['id']}")
    head = R.header(kind="Hitter evaluation · R&D advance report", name=d["name"], meta=meta, rmeta=rmeta)
    slash = f"{S.rate3(row.get('AVG'))}/{S.rate3(row.get('OBP'))}/{S.rate3(row.get('SLG'))}"
    line = R.statline([
        ("PA", S.num(row.get("PA"), 0), None),
        ("AVG/OBP/SLG", slash, _p(row, "OBP")),
        ("wOBA", S.rate3(row.get("wOBA")), _p(row, "wOBA")),
        ("xwOBA", S.rate3(row.get("xwOBA")), _p(row, "xwOBA")),
        ("wRC+", S.num(row.get("wRC+"), 0), _p(row, "wRC+")),
        ("HR", S.num(row.get("HR"), 0), None),
        ("K%", S.pct(row.get("K%"), 1), _p(row, "K%")),
        ("BB%", S.pct(row.get("BB%"), 1), _p(row, "BB%")),
        ("Barrel%", S.pct(row.get("barrel_pct"), 1), _p(row, "barrel_pct")),
        ("Hard-hit%", S.pct(row.get("hard_pct"), 1), _p(row, "hard_pct")),
        ("Avg / max EV", (f"{S.num(row.get('ev_mean'), 1)}<span class='muted' style='font-size:7.5pt'> / "
                          f"{S.num(row.get('ev_max'), 1)}</span>"), _p(row, "ev_mean")),
        ("Spd (FG)", S.num(row.get("Spd"), 1), _p(row, "Spd")),
    ], widths=[0.8, 2.05, 1, 1, 0.9, 0.7, 1, 1, 1.05, 1.1, 1.55, 0.85])
    pool_note = f"vs {int(ctx.batters['qualified'].sum())} hitters ≥1,000 pitches"
    grades = R.grades_panel("20–80 grades", [
        ("Hit", row.get("g_hit"), 100 * row.get("p_hit", np.nan), f"Contact {S.pct(row.get('contact_pct'))}"),
        ("Power", row.get("g_power"), 100 * row.get("p_power", np.nan), f"Barrel {S.pct(row.get('barrel_pct'), 1)}"),
        ("Discipline", row.get("g_discipline"), 100 * row.get("p_discipline", np.nan), f"Chase {S.pct(row.get('chase_pct'))}"),
        ("Pull-air", row.get("g_pull_air"), 100 * row.get("p_pull_air", np.nan), f"{S.pct(row.get('pull_air_pct'))} of BBE"),
        ("Speed (Spd)", row.get("g_speed"), 100 * row.get("p_speed", np.nan), f"Spd {S.num(row.get('Spd'), 1)}"),
    ], note=pool_note + ("" if row.get("qualified") else " · <span class=flag>below qualifying sample</span>"),
        extra="<div class='gr' style='grid-template-columns:74px 1fr 1fr 1fr'><span class='gl'>vs pitch group</span>" + "".join(
            f"<span style='white-space:nowrap'>{S.grade_chip(row.get(f'g_vs_{g}'), big=True)} "
            f"<span class='muted' style='font-size:6.2pt'>{lab} {S.signed(row.get(f'rv100_{g}'), 1)}</span></span>"
            for g, lab in (("FB", "FB"), ("BRK", "BRK"), ("OFF", "OFF"))) + "</div>")
    top = (f'<div class="row"><div class="col" style="flex:1.75">{R.bottom_line(d["bullets"])}</div>'
           f'<div class="col" style="flex:1">{grades}</div></div>')
    maps = _maps_section(d)
    body = (f'<div class="row"><div class="col" style="flex:1.22">{_bands_section(d)}</div>'
            f'<div class="col" style="flex:1">{_spray_section(d)}</div></div>')
    foot = R.footer(kind="Hitter evaluation", through=ctx.date_range[1], page=1, pages=2,
                    notes="Grades: league percentile → 20–80 (50 avg, 10 = 1 SD); method on p.2. " + R.color_legend())
    return head + line + top + maps + body + foot


def _maps_section(d: dict[str, Any]) -> str:
    ctx: LeagueContext = d["ctx"]
    zg = ctx.zone_groups
    maps = d["maps"]

    def lg(grp: str, zid: str, col: str) -> float:
        try:
            return float(zg.loc[(grp, zid), col])
        except KeyError:
            return float("nan")

    def seq(_zid: str, v: float) -> str:
        return S.seq_color(min(max(v, 0.0), 1.0) * 0.95)

    metric_rows = [
        ("Swing %", "swing", "n_all", 12, lambda v: f"{v * 100:.0f}", None),
        ("Whiff / swing", "whiff", "n_sw", 8, lambda v: f"{v * 100:.0f}", -0.40),
        ("xwOBA on contact", "xwcon", "n_bip", 5, lambda v: f"{v:.3f}"[1:] if v < 1 else f"{v:.1f}", 0.50),
    ]
    cols = [(h, g) for h in ("R", "L") for g in ("FB", "BRK", "OFF")]
    head = "<div class='hd'></div>" + "".join(
        f"<div class='hd'><b>{GROUP_NAMES[g]}</b><br>vs {h}HP · n={maps[(h, g)]['n']}</div>" for h, g in cols)
    cells = [head]
    for label, key, nkey, min_n, fmt, scale in metric_rows:
        cells.append(f"<div class='hd' style='writing-mode:vertical-rl;transform:rotate(180deg);text-align:center;"
                     f"color:#1b1f24;font-weight:700'>{label}</div>")
        for h, g in cols:
            m = maps[(h, g)]
            if scale is None:
                color = seq
            else:
                def color(zid: str, v: float, g=g, key=key, scale=scale) -> str:
                    ref = lg(g, zid, key)
                    if not np.isfinite(ref):
                        return "#f4f4f2"
                    return R.tint(float(np.clip(0.5 + (v - ref) / scale, 0, 1)), 0.85)
            cells.append(S.zone_grid(m[key], m[nkey], stand=m["stand"], color=color, fmt=fmt, min_n=min_n, cell=13.8))
    grid = (f"<div class='mini-grid' style='grid-template-columns:12px repeat(6, 1fr);justify-items:center;gap:1px 2px'>"
            f"{''.join(cells)}</div>")
    title = _maps_title(d)
    sub = ("Catcher's view, 13 zones (3×3 strike zone + 4 chase quadrants); hitter-relative, so 'in' flips by side. "
           "Swing%: darker = swings more (frequency, not quality). Whiff and xwOBA on contact are tinted vs the league rate "
           "in the same zone and pitch group (red = better for the hitter). Grey = small sample "
           "(&lt;12 pitches, &lt;8 swings, &lt;5 balls in play).")
    return R.section(title, sub, grid, tag="Zones", style="margin-top:6px")


def _maps_title(d: dict[str, Any]) -> str:
    """Name the single most damaging and most whiff-prone zone × group cells (min samples)."""
    ctx = d["ctx"]
    best, worst = None, None
    for (h, g), m in d["maps"].items():
        for zid, v in m["xwcon"].items():
            if m["n_bip"].get(zid, 0) >= 12 and _ok(v):
                lgv = float(ctx.zone_groups["xwcon"].get((g, zid), np.nan))
                if np.isfinite(lgv) and (best is None or v - lgv > best[0]):
                    best = (v - lgv, h, g, zid, v)
        for zid, v in m["whiff"].items():
            if m["n_sw"].get(zid, 0) >= 20 and _ok(v):
                lgv = float(ctx.zone_groups["whiff"].get((g, zid), np.nan))
                if np.isfinite(lgv) and (worst is None or v - lgv > worst[0]):
                    worst = (v - lgv, h, g, zid, v, lgv)
    parts = []
    if best:
        parts.append(f"damage on {GROUP_NAMES[best[2]].lower()} {zone_label(best[3]).lower()} vs {best[1]}HP "
                     f"({best[4]:.3f} xwOBAcon)".replace("0.", "."))
    if worst:
        parts.append(f"misses {GROUP_NAMES[worst[2]].lower()} {zone_label(worst[3]).lower()} vs {worst[1]}HP "
                     f"({worst[4] * 100:.0f}% whiff vs {worst[5] * 100:.0f}% league)")
    return "Swing decisions &amp; damage — " + "; ".join(parts) if parts else "Swing decisions &amp; damage"


def _bands_section(d: dict[str, Any]) -> str:
    rows = []
    for b in d["perf"]:
        if b["n"] == 0:
            continue
        small = b["n"] < 80
        wp = None if small or not _ok(b["whiff"]) else 100 * float(np.clip(0.5 - (b["whiff"] - b["lg_whiff"]) / 0.24, 0, 1))
        xp = None if b["bip"] < 15 or not _ok(b["xwcon"]) else 100 * float(np.clip(0.5 + (b["xwcon"] - b["lg_xwcon"]) / 0.24, 0, 1))
        rp = None if small or not _ok(b["rv100"]) else 100 * float(np.clip(0.5 + (b["rv100"] - b["lg_rv100"]) / 6, 0, 1))
        cp = None if small or not _ok(b["chase"]) else 100 * float(np.clip(0.5 - (b["chase"] - b["lg_chase"]) / 0.2, 0, 1))
        rows.append(
            f"<tr class='{'small' if small else ''}'><td class='l'><b>{S.esc(b['label'])}</b></td><td>{int(b['n'])}</td>"
            f"<td>{S.pct(b['swing'])}</td>{R.pct_cell(S.pct(b['whiff']), wp)}{R.pct_cell(S.pct(b['chase']), cp)}"
            f"{R.pct_cell(S.rate3(b['xwcon']), xp)}<td>{S.rate3(b['xwoba'])}</td>"
            f"{R.pct_cell(S.signed(b['rv100'], 1), rp)}<td class='muted'>{S.signed(b['lg_rv100'], 1)}</td></tr>"
        )
    head = ("<thead><tr><th class='l'>Pitch / band</th><th>n</th><th>Swing</th><th>Whiff</th><th>Chase</th>"
            "<th>xwOBAcon</th><th>xwOBA</th><th>RV/100</th><th>Lg</th></tr></thead>")
    ok = [b for b in d["perf"] if b["n"] >= 80 and _ok(b["rv100"]) and _ok(b["lg_rv100"])]
    title = "vs pitch type &amp; velo/movement bands"
    if ok:
        best = max(ok, key=lambda b: b["rv100"] - b["lg_rv100"])
        worst = min(ok, key=lambda b: b["rv100"] - b["lg_rv100"])
        title = (f"Pitch types — best vs {best['label'].lower()} ({S.signed(best['rv100'], 1)} RV/100), "
                 f"worst vs {worst['label'].lower()} ({S.signed(worst['rv100'], 1)})")
    sub = ("All pitches seen, both hands. RV/100 = hitter run value per 100 pitches (+ = good for him); Lg = league "
           "average for the band. Tints vs league band rates; grey rows n &lt; 80. FF bands overlap (velo and ride).")
    return R.section(title, sub, f"<table class='tbl'>{head}<tbody>{''.join(rows)}</tbody></table>", tag="Pitch types")


def _spray_section(d: dict[str, Any]) -> str:
    sp = d["spray"]
    mix, a = sp["mix"], d["align"]
    field = S.spray_field(sp["balls"], standard=a["standard"] if a else None, optimized=a["optimized"] if a else None,
                          w=262, h=170)
    lg = mix["lg"]
    keys = [("pull", "Pull"), ("center", "Cent"), ("oppo", "Oppo"), ("pull_air", "Pull-air"),
            ("gb", "GB"), ("ld", "LD"), ("fb", "FB"), ("pu", "PU")]
    stats = ("<table class='tbl' style='margin-top:2px'><thead><tr><th class='l'>BIP mix</th>"
             + "".join(f"<th>{lab}</th>" for _, lab in keys) + "</tr></thead><tbody>"
             + f"<tr><td class='l'><b>{S.esc(d['name'].split()[-1])}</b> <span class='muted'>n={mix['n']}</span></td>"
             + "".join(f"<td><b>{mix[k] * 100:.0f}%</b></td>" for k, _ in keys) + "</tr>"
             + "<tr><td class='l muted'>League</td>"
             + "".join(f"<td class='muted'>{lg[k] * 100:.0f}%</td>" for k, _ in keys) + "</tr></tbody></table>")
    if a:
        moves = describe_moves(a["moves"][:3]) or "no material moves"
        rec = (f"<div class='note' style='margin-top:3px'><b>Alignment:</b> {S.signed(a['delta_per100'], 1)} outs per 100 BIP vs "
               f"standard, cross-validated ({S.signed(a['delta_in_sample'], 1)} in-sample; n={a['n']} BIP batting "
               f"{d['stand']}). {S.esc(moves)}.</div>")
        title = (f"Spray — {mix['pull'] * 100:.0f}% pulled; shift-legal alignment adds "
                 f"{S.signed(a['delta_per100'], 1)} outs/100 BIP (cross-validated)")
    else:
        rec = "<div class='note muted'>Too few balls in play for an alignment recommendation (&lt; 60).</div>"
        title = f"Spray — {mix['pull'] * 100:.0f}% pulled"
    sub = ("All balls in play (grey out, red hit, dark red HR). Hollow = standard alignment, navy = optimized "
           "(2 IF each side of 2B, IF on dirt).")
    body = f"<div style='display:flex;justify-content:center'>{field}</div>{stats}{rec}"
    return R.section(title, sub, body, tag="Spray")


def _page2(d: dict[str, Any]) -> str:
    ctx: LeagueContext = d["ctx"]
    bats = {"L": "Bats L", "R": "Bats R", "S": "Switch"}[d["bats"]]
    head = R.header(kind="Hitter evaluation · continued", name=d["name"], meta="",
                    rmeta=f"{d['team']} · {bats} · {ctx.season} · through <b>{ctx.date_range[1]}</b>", compact=True)
    body = (_attack_section(d) + _counts_section(d)
            + f'<div class="row"><div class="col" style="flex:1.05">{_trend_section(d)}</div>'
              f'<div class="col" style="flex:1">{_splits_section(d)}{_comps_section(d)}</div></div>')
    method = R.method_block([
        ("Grades", ("z-score composites → percentile within hitters with ≥1,000 pitches seen → 50 + 10·Φ⁻¹(p), clipped "
         "20–80, shown to the nearest 5. Hit = contact%, xBA, K%, whiff vs FB/BRK. Power = barrel%, EV90, max EV, ISO, "
         "hard-hit%. Discipline = chase%, zone-swing minus chase, BB%. Pull-air = pulled fly balls/liners share. Speed = "
         "FanGraphs Spd (sprint speed is not in this dataset). vs-pitch grades = hitter RV/100 by pitch group.")),
        ("Models", ("attack plan = situational pitch-type model scored against a league-average arsenal from each hand "
         "(this hitter's priors), then the location model's best zone for that pitch; alignment = shift-legal "
         "greedy optimizer over his balls in play with a catch-probability fielding model, gain reported 2-fold "
         "cross-validated (fit on half his BIP, scored on the other half). Predicted xwOBA gaps are "
         "small — the cited zone stats are his actual results.")),
        ("Caveats", ("single season, regular season only; zone cells with small samples greyed; xwOBA ignores park; "
         "alignment model is approximate (no runner/game state).")),
    ])
    foot = R.footer(kind="Hitter evaluation", through=ctx.date_range[1], page=2, pages=2,
                    notes="Counts are balls-strikes before the pitch. " + R.color_legend())
    return head + body + method + foot


def _attack_section(d: dict[str, Any]) -> str:
    plan = d["attack"]
    if plan is None or plan.empty:
        return R.section("How to attack", "Attack plan unavailable (model or sample missing).", "", tag="Attack")
    sup = d["zone_support"]
    hands = [h for h in ("R", "L") if (plan["hand"] == h).any()]
    head = "<thead><tr><th class='l'>Count</th>" + "".join(
        f"<th class='l sep' colspan='3'>vs {h}HP</th>" for h in hands) + "</tr></thead>"
    rows = []
    for bucket in BUCKETS:
        tds = [f"<td class='l'><b>{bucket}</b><div class='muted' style='font-size:5.8pt'>{', '.join(BUCKETS[bucket])}</div></td>"]
        for h in hands:
            r = plan[(plan["hand"] == h) & (plan["bucket"] == bucket)]
            if r.empty:
                tds.append("<td class='sep' colspan='3'>–</td>")
                continue
            r = r.iloc[0]
            col = S.PITCH_COLORS.get(r["pitch_type"], S.MUTED)
            zone = zone_label(r["zone"]) if r["zone"] else "—"
            zs = sup.get((h, r["pitch_type"], r["zone"]))
            ev = (f"rarely pitched there: {zs['n']} {zs['grp_name'].lower()} all season" if zs else "")
            if zs and zs["n"] >= 15:
                bits = [f"n={zs['n']}"]
                if _ok(zs["whiff"]):
                    bits.insert(0, f"{zs['whiff'] * 100:.0f}% whiff")
                if _ok(zs["xwcon"]):
                    bits.insert(1, f"{zs['xwcon']:.3f} xwOBAcon".lstrip("0"))
                ev = f"his {zs['grp_name'].lower()} there: " + " · ".join(bits)
            tds.append(
                f"<td class='l sep'><b style='color:{col}'>{PITCH_NAMES.get(r['pitch_type'], r['pitch_type'])}</b> → {zone}"
                f"<div class='muted' style='font-size:5.9pt'>{ev}</div></td>"
                f"<td>{S.rate3(r['pred_xwoba'])}<div class='muted' style='font-size:5.9pt'>2nd {r['second']} {S.rate3(r['second_xwoba'])}</div></td>"
                f"<td class='l'><span class='muted'>avoid</span> <b>{r['worst']}</b> {S.rate3(r['worst_xwoba'])}</td>"
            )
        rows.append(f"<tr>{''.join(tds)}</tr>")
    two = plan[plan["bucket"] == "Two-strike"]
    title = "How to attack"
    if not two.empty:
        r = two.iloc[0]
        title = (f"How to attack — finish with {PITCH_NAMES.get(r['pitch_type'], r['pitch_type']).lower()} "
                 f"{zone_label(r['zone']).lower() if r['zone'] else ''} vs {r['hand']}HP")
    sub = ("Model-preferred pitch (lowest expected xwOBA vs this hitter from a league-average arsenal) and its best "
           "location, by count bucket and pitcher hand; second-best and the pitch to avoid with expected xwOBA. "
           "Grey line = his actual results on that pitch group in that zone.")
    return R.section(title, sub, f"<table class='tbl'>{head}<tbody>{''.join(rows)}</tbody></table>", tag="Attack")


def _counts_section(d: dict[str, Any]) -> str:
    t, row, ctx = d["counts"], d["row"], d["ctx"]
    hdr = "".join(f"<th class='c'>{c}</th>" for c in COUNTS)

    def line(label: str, key: str, fmt: Any, scale: float, sign: int) -> str:
        tds = []
        for c in COUNTS:
            v, ref, n = t.loc[c, key], t.loc[c, f"lg_{key}"], t.loc[c, "n"]
            if not _ok(v):
                tds.append("<td class='c muted'>–</td>")
                continue
            small = (n < 25) or (key == "xwcon" and t.loc[c, "bip"] < 8)
            bg = "transparent" if small or not _ok(ref) or sign == 0 else R.tint(float(np.clip(0.5 + sign * (v - ref) / scale, 0, 1)))
            diff = "" if not _ok(ref) or key == "xwcon" else f"<div class='muted' style='font-size:5.6pt'>{S.signed((v - ref) * 100, 0)}</div>"
            tds.append(f"<td class='c{' muted' if small else ''}' style='background:{bg}'>{fmt(v)}{diff}</td>")
        return f"<tr><td class='l'>{label}</td>{''.join(tds)}</tr>"

    body = (f"<table class='tbl'><thead><tr><th class='l'>By count</th>{hdr}</tr></thead><tbody>"
            + "<tr><td class='l'>Pitches</td>" + "".join(f"<td class='c muted'>{int(t.loc[c, 'n']) if _ok(t.loc[c, 'n']) else 0}</td>" for c in COUNTS) + "</tr>"
            + line("Swing %", "swing", lambda v: f"{v * 100:.0f}", 0.2, 0)
            + line("Chase %", "chase", lambda v: f"{v * 100:.0f}", 0.2, -1)
            + line("Whiff / swing", "whiff", lambda v: f"{v * 100:.0f}", 0.2, -1)
            + line("xwOBA on contact", "xwcon", lambda v: f"{v:.3f}".lstrip("0"), 0.25, 1)
            + "</tbody></table>")
    fp, c2 = row.get("fp_swing_pct"), row.get("chase_2k")
    lfp, lc2 = ctx.league.get("fp_swing_pct"), ctx.league.get("chase_2k")
    bits = []
    if _ok(fp):
        bits.append(f"swings at {fp * 100:.0f}% of first pitches (league {lfp * 100:.0f}%)")
    if _ok(c2):
        bits.append(f"chases {c2 * 100:.0f}% with two strikes (league {lc2 * 100:.0f}%)")
    title = "Count tendencies — " + "; ".join(bits) if bits else "Count tendencies"
    sub = ("Small numbers = percentage-point difference from league in that count. Chase/whiff tinted vs league "
           "(red = better for the hitter); xwOBA on contact tinted vs league. Grey = n &lt; 25 pitches.")
    return R.section(title, sub, body, tag="Counts")


def _trend_section(d: dict[str, Any]) -> str:
    tr, ctx = d["trend"], d["ctx"]
    games = tr["games"]
    lo, hi = pd.Timestamp(ctx.date_range[0]), pd.Timestamp(ctx.date_range[1])
    flags = {f["key"]: f for f in tr["flags"]}
    cells = []
    for key, label, _thr, fmt in TREND_SPECS:
        f = flags.get(key)
        cap = f"{label} — {ROLL_GAMES}-game rolling"
        if f:
            cap += f" <span class='flag'>⚑ {f['recent_txt']} vs {f['base_txt']}</span>"
        num_fmt = "{:.3f}" if key == "xwoba" else ("{:.1f}" if key == "ev" else "{:.2f}")
        chart = S.trend_chart(games["date"], games[key], w=330, h=112, rolling=1, fmt=num_fmt, stints=d["stints"],
                              baseline=tr["season"][key], flag_from=f["since"] if f else None, date_range=(lo, hi))
        cells.append(f"<div><div style='font-size:6.6pt;font-weight:600'>{cap}</div>{chart}</div>")
    title = "Trends — steady relative to his season line"
    if tr["flags"]:
        f = tr["flags"][0]
        title = f"Trends — {f['label'][0].lower() + f['label'][1:]} {'up' if f['delta'] > 0 else 'down'} lately ({f['recent_txt']} vs {f['base_txt']})"
    stint_txt = "; ".join(
        f"{R.fmt_date(s['start'])}–{R.fmt_date(s['end']) if s.get('end') is not None else 'season end'}"
        + (f" ({S.esc(s['reason'][:40])})" if s.get("reason") else "") for s in d["stints"])
    sub = (f"{ROLL_GAMES}-game rolling (min 5 games); dashed = season. ⚑ = latest window differs by ≥.045 xwOBA, "
           f"2 mph EV or 5 pts chase. " + (f"Grey = IL: {stint_txt}." if stint_txt else "No IL stints."))
    return R.section(title, sub, "".join(cells), tag="Trends")


def _splits_section(d: dict[str, Any]) -> str:
    sp, ctx = d["splits"], d["ctx"]
    lg = ctx.league.get("xwoba_pa", 0.315)
    head = ("<thead><tr><th class='l'>Split</th><th>PA</th><th>AVG</th><th>wOBA</th><th>xwOBA</th><th>K%</th><th>BB%</th>"
            "<th>HR</th><th>Barrel</th><th>Chase</th></tr></thead>")
    rows = []
    for lab, s in sp.items():
        small = s["pa"] < 60
        p = None if small or not _ok(s["xwoba"]) else 100 * float(np.clip(0.5 + (s["xwoba"] - lg) / 0.12, 0, 1))
        rows.append(f"<tr class='{'small' if small else ''}'><td class='l'><b>{lab}</b></td><td>{s['pa']}</td>"
                    f"<td>{S.rate3(s['avg'])}</td><td>{S.rate3(s['woba'])}</td>{R.pct_cell(S.rate3(s['xwoba']), p)}"
                    f"<td>{S.pct(s['k'], 1)}</td><td>{S.pct(s['bb'], 1)}</td><td>{s['hr']}</td>"
                    f"<td>{S.pct(s['barrel'], 1)}</td><td>{S.pct(s['chase'])}</td></tr>")
    r, l_ = sp["vs RHP"], sp["vs LHP"]
    title = "Platoon"
    if _ok(r["xwoba"]) and _ok(l_["xwoba"]):
        gap = (r["xwoba"] - l_["xwoba"]) * 1000
        title = ("Platoon — no meaningful split" if abs(gap) < 25 else
                 f"Platoon — {abs(gap):.0f}-pt xwOBA edge vs {'RHP' if gap > 0 else 'LHP'}")
    sub = f"Statcast PAs. xwOBA tint vs league {S.rate3(lg)} (red = better for the hitter). Grey: &lt; 60 PA."
    return R.section(title, sub, f"<table class='tbl'>{head}<tbody>{''.join(rows)}</tbody></table>", tag="Splits")


def _comps_section(d: dict[str, Any]) -> str:
    comps = d["comps"]
    rows = "".join(
        f"<div class='comp'><span class='nm'>{S.esc(c['name'])} <span class='muted'>{S.esc(c['team'])}</span> "
        f"<span class='muted' style='font-weight:400;font-size:6pt'>Hit</span> {S.grade_chip(c['hit'])} "
        f"<span class='muted' style='font-weight:400;font-size:6pt'>Pwr</span> {S.grade_chip(c['power'])}</span>"
        f"<span><span class='simbar'><span style='width:{c['sim'] * 100:.0f}%'></span></span>"
        f"<span class='muted' style='font-size:6.3pt'>{c['sim'] * 100:.0f}% similar</span></span>"
        f"<span class='d'>{c['note']}</span></div>"
        for c in comps
    )
    title = f"Comps — closest offensive profile: {comps[0]['name']}" if comps else "Comps"
    sub = ("Nearest qualified hitters on barrel%, EV90, contact, chase, zone swing, pull-air, GB%, launch angle, whiff by "
           "pitch group, BB% and K% (standardized, weighted).")
    return R.section(title, sub, rows, tag="Comps")


def render_hitter_html(d: dict[str, Any], *, screen_links: list[tuple[str, str]] | None = None) -> str:
    d["bullets"] = narrative.select(d["findings"])
    return R.document(f"{d['name']} — Hitter evaluation ({d['ctx'].season})", [_page1(d), _page2(d)], screen_links=screen_links)
