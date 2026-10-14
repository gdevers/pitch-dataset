"""Two-page pitcher evaluation report: data assembly + HTML rendering."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from pitch_dataset.reports import narrative
from pitch_dataset.reports import render as R
from pitch_dataset.reports import svg as S
from pitch_dataset.reports.context import (
    FAMILY_NAMES,
    MIN_PITCH_TYPE_N,
    PITCH_NAMES,
    LeagueContext,
    current_team,
    il_stints,
    player_pitches,
)
from pitch_dataset.reports.grades import display_grade, grade_word
from pitch_dataset.reports.models import (
    COUNTS,
    optimizer_suggestion,
    pitcher_count_plan,
)

log = logging.getLogger(__name__)

BUCKET_OF = {"0-0": "First", "0-1": "Ahead", "0-2": "Ahead", "1-2": "Ahead", "1-0": "Behind", "2-0": "Behind",
             "3-0": "Behind", "2-1": "Behind", "3-1": "Behind", "1-1": "Even", "2-2": "Even", "3-2": "Even"}
TREND_SPECS = [  # key, label, unit, flag threshold, fmt
    ("fb_velo", "Primary FB velo", "mph", 1.0, "{:.1f}"),
    ("fb_spin", "Primary FB spin", "rpm", 75.0, "{:.0f}"),
    ("rel_z", "Release height", "ft", 0.2, "{:.2f}"),
    ("ext", "Extension", "ft", 0.2, "{:.2f}"),
]


def pitch_label(pt: str) -> str:
    return PITCH_NAMES.get(pt, pt)


def _arsenal(ctx: LeagueContext, pid: int, df: pd.DataFrame) -> pd.DataFrame:
    pt = ctx.pitch_types[ctx.pitch_types["pitcher"] == pid].copy()
    pt = pt[(pt["n"] >= 15) & pt["fam"].notna()].sort_values("n", ascending=False)
    if pt.empty:
        return pt
    for stand in ("L", "R"):
        side = df[df["stand"] == stand]["pitch_type"].value_counts(normalize=True)
        pt[f"vs{stand}"] = pt["pitch_type"].map(side).fillna(0.0)
    bucket = df["count"].map(BUCKET_OF)
    for b in ("First", "Ahead", "Behind", "Even"):
        share = df[bucket == b]["pitch_type"].value_counts(normalize=True)
        pt[f"b_{b}"] = pt["pitch_type"].map(share).fillna(0.0)
    two = df[df["strikes"] == 2]["pitch_type"].value_counts(normalize=True)
    pt["b_2K"] = pt["pitch_type"].map(two).fillna(0.0)
    pool = ctx.pitch_types[ctx.pitch_types["qualified"]]
    pt["pool_n"] = pt["pool_key"].map(pool["pool_key"].value_counts()).fillna(0).astype(int)
    pt["name"] = pt["pitch_type"].map(pitch_label)
    return pt.reset_index(drop=True)


def _signature_rank(ctx: LeagueContext, row: pd.Series) -> dict[str, Any] | None:
    """The pitch's most extreme shape trait vs its pool (rank among qualified peers)."""
    pool = ctx.pitch_types[ctx.pitch_types["qualified"] & (ctx.pitch_types["pool_key"] == row["pool_key"])]
    if len(pool) < 15:
        return None
    fam = row["fam"]
    traits = [("velo", "velo", 1, "mph", "{:.1f}")]
    if fam in ("FF",):
        traits.append(("ride", "ivb", 1, "in IVB", "{:.1f}"))
    if fam in ("SI", "CH", "FS"):
        traits.append(("arm-side run", "hb_arm", 1, "in HB", "{:.1f}"))
    if fam in ("SL", "ST", "CU", "FC"):
        traits.append(("sweep", "hb_arm", -1, "in glove-side HB", "{:.1f}"))
    if fam in ("CU", "CH", "FS", "SL"):
        traits.append(("drop", "ivb", -1, "in IVB", "{:.1f}"))
    traits.append(("spin", "spin", 1, "rpm", "{:.0f}"))
    best = None
    for word, col, sign, unit, fmt in traits:
        vals = pool[col] * sign
        v = row[col] * sign
        if not np.isfinite(v):
            continue
        rank = int((vals > v).sum()) + 1
        if best is None or rank < best["rank"]:
            shown = row[col] if sign > 0 else abs(row[col])
            best = {"word": word, "rank": rank, "of": len(pool), "value": fmt.format(shown), "unit": unit}
    return best


def _count_strategy(df: pd.DataFrame, plan: pd.DataFrame, arsenal: list[str]) -> dict[str, Any]:
    use = df[df["pitch_type"].isin(arsenal)]
    grid: dict[tuple[str, str], dict[str, Any]] = {}
    predictable, gaps = [], []
    for (stand, count), g in use.groupby(["stand", "count"]):
        vc = g["pitch_type"].value_counts()
        top, share = vc.index[0], vc.iloc[0] / len(g)
        cell = {"n": len(g), "top": top, "share": share, "model": None, "delta": np.nan}
        if not plan.empty:
            p = plan[(plan["stand"] == stand) & (plan["count"] == count)].set_index("pitch_type")["pred_xwoba"]
            if len(p):
                cell["model"] = p.idxmin()
                usage = g["pitch_type"].value_counts(normalize=True).reindex(p.index).fillna(0)
                cell["mix_xw"] = float((usage * p).sum() / max(usage.sum(), 1e-9))
                cell["delta"] = float(cell["mix_xw"] - p.min())
                cell["top_xw"] = float(p.get(top, np.nan))
                cell["model_xw"] = float(p.min())
        grid[(stand, count)] = cell
        if len(g) >= 25:
            predictable.append({"stand": stand, "count": count, "pitch_type": top, "share": share, "n": len(g)})
        if cell["model"] and cell["model"] != top and len(g) >= 25 and np.isfinite(cell["delta"]):
            gaps.append({"stand": stand, "count": count, "top": top, "share": share, "model": cell["model"],
                         "top_xw": cell["top_xw"], "model_xw": cell["model_xw"], "delta": cell["delta"], "n": len(g)})
    predictable.sort(key=lambda r: -r["share"])
    gaps.sort(key=lambda r: -(r["top_xw"] - r["model_xw"]) * np.sqrt(r["n"]))
    return {"grid": grid, "predictable": predictable[:4], "gaps": gaps[:3]}


def _sequencing(df: pd.DataFrame, arsenal: list[str]) -> dict[str, Any]:
    d = df.sort_values(["game_pk", "at_bat_number", "pitch_number"])
    d = d.assign(prev=d.groupby(["game_pk", "at_bat_number"])["pitch_type"].shift(1))
    d = d[d["prev"].isin(arsenal) & d["pitch_type"].isin(arsenal)]
    trans = pd.crosstab(d["prev"], d["pitch_type"], normalize="index").reindex(index=arsenal, columns=arsenal).fillna(0)
    counts = d["prev"].value_counts()
    base = df[df["swing"]].groupby("pitch_type")["whiff"].mean()
    rows = []
    for (a, b), g in d[d["swing"]].groupby(["prev", "pitch_type"]):
        if a == b or len(g) < 35:
            continue
        w = g["whiff"].mean()
        rows.append({"prev": a, "next": b, "whiff": w, "base": base.get(b, np.nan), "swings": len(g),
                     "lift": w - base.get(b, np.nan)})
    rows.sort(key=lambda r: -r["lift"] * np.sqrt(r["swings"]))
    return {"trans": trans, "n_prev": counts, "whiff_after": rows[:3]}


def _tunnel(df: pd.DataFrame) -> dict[str, Any] | None:
    from pitch_dataset.zone3d import _PHYSICS_COLS, _derive, _tunnel_stats

    need = [c for c in _PHYSICS_COLS if c in df.columns]
    sub = df.dropna(subset=need)
    sub = sub[sub["vy0"] < 0]
    if len(sub) < 200:
        return None
    try:
        cols = list(dict.fromkeys(need + ["pitch_type", "release_speed", "pfx_x", "pfx_z", "description", "hc_x", "hc_y",
                                          "hit_distance_sc", "plate_x", "plate_z", "stand", "sz_top", "sz_bot"]))
        der = _derive(sub[cols].reset_index(drop=True))
        return _tunnel_stats(der)
    except Exception:
        log.exception("Tunnel stats failed")
        return None


def _trends(df: pd.DataFrame, fb_fam: str | None, stints: list[dict[str, Any]]) -> dict[str, Any]:
    g = df.groupby("game_pk")
    games = pd.DataFrame({
        "date": g["game_date"].first(), "n": g.size(),
        "rel_z": g["release_pos_z"].mean(), "ext": g["release_extension"].mean(),
    })
    if fb_fam:
        fb = df[df["fam"] == fb_fam].groupby("game_pk")
        games["fb_velo"] = fb["release_speed"].mean()
        games["fb_spin"] = fb["release_spin_rate"].mean()
    games = games.sort_values("date").reset_index(drop=True)
    flags = []
    if len(games) >= 10:
        base, recent = games.iloc[:-5], games.iloc[-5:]
        for key, label, unit, thr, fmt in TREND_SPECS:
            if key not in games:
                continue
            b, r = float(base[key].median()), float(recent[key].mean())
            if np.isfinite(b) and np.isfinite(r) and abs(r - b) >= thr:
                flags.append({"key": key, "label": label, "unit": unit, "base": b, "recent": r, "delta": r - b,
                              "fmt": fmt, "since": recent["date"].iloc[0]})
    post_il = None
    done = [s for s in stints if s.get("end") is not None]
    if done and fb_fam and "fb_velo" in games:
        s = done[-1]
        pre = games[games["date"] < s["start"]]["fb_velo"]
        post = games[games["date"] >= s["end"]]["fb_velo"]
        if len(pre) >= 3 and len(post) >= 3:
            post_il = {"end": s["end"], "pre": float(pre.mean()), "post": float(post.mean()), "n_post": len(post)}
    return {"games": games, "flags": flags, "post_il": post_il}


def _comps(ctx: LeagueContext, pid: int) -> list[dict[str, Any]]:
    pit, pt = ctx.pitchers, ctx.pitch_types
    pool_ids = pit.index[pit["qualified"]].tolist()
    if pid not in pool_ids:
        pool_ids.append(pid)
    usage = pt.pivot_table(index="pitcher", columns="fam", values="usage", aggfunc="sum").reindex(pool_ids).fillna(0)
    brk = pt[pt["fam"].isin(["SL", "ST", "CU"])].sort_values("n", ascending=False).drop_duplicates("pitcher").set_index("pitcher")
    feats = pd.DataFrame(index=pool_ids)
    for fam in usage.columns:
        feats[f"u_{fam}"] = usage[fam]
    feats["fb_velo"] = pit["fb_velo"]
    feats["fb_ivb"] = pit["fb_ivb"]
    feats["fb_hb"] = pit["fb_hb"]
    arm = pt.assign(w=pt["arm_angle"] * pt["n"]).groupby("pitcher")[["w", "n"]].sum()
    feats["arm"] = arm["w"] / arm["n"]
    feats["brk_dv"] = brk["velo"] - pit["fb_velo"]
    feats["brk_hb"] = brk["hb_arm"]
    feats["brk_ivb"] = brk["ivb"]
    feats["whiff"] = pit["whiff_pct"]
    feats["zone"] = pit["zone_pct"]
    weights = {c: 0.6 for c in feats.columns if c.startswith("u_")}
    weights.update({"fb_velo": 1.3, "fb_ivb": 1.0, "fb_hb": 1.0, "arm": 1.0, "brk_dv": 0.7, "brk_hb": 0.7,
                    "brk_ivb": 0.7, "whiff": 0.9, "zone": 0.5})
    z = (feats - feats.mean()) / feats.std().replace(0, 1)
    z = z.fillna(0) * pd.Series(weights)
    me = z.loc[pid]
    dist = np.sqrt(((z - me) ** 2).sum(axis=1)).drop(pid)
    ref = float(np.median(np.sqrt(((z.sample(min(200, len(z)), random_state=1).to_numpy()[:, None, :]
                                     - z.sample(min(200, len(z)), random_state=2).to_numpy()[None, :, :]) ** 2).sum(axis=2))))
    out = []
    for oid, d in dist.nsmallest(3).items():
        row = pit.loc[oid]
        mix = usage.loc[oid].sort_values(ascending=False)
        mix_txt = " / ".join(f"{f} {v * 100:.0f}%" for f, v in mix.items() if v >= 0.08)
        team = current_team(ctx.data_dir, ctx.season, int(oid)) or str(row.get("fg_team") or "")
        out.append({
            "id": int(oid), "name": ctx.name(oid), "team": "" if team.startswith("-") else team, "sim": max(0.0, 1 - d / ref),
            "note": f"{row['p_throws']}HP {row['role']} · FB {row['fb_velo']:.1f} mph, {row['fb_ivb']:.0f}\" IVB · {mix_txt}",
            "stuff": row.get("g_stuff"),
        })
    return out


def _shape_note(ctx: LeagueContext, ars: pd.DataFrame, pid: int) -> dict[str, Any] | None:
    """Weakest-Stuff pitch (≥10% usage) vs top-quartile Stuff peers in its pool: biggest shape gap."""
    cand = ars[(ars["usage"] >= 0.10) & ars["g_stuff"].notna()].sort_values("g_stuff")
    if cand.empty:
        return None
    row = cand.iloc[0]
    if row["g_stuff"] >= 50:
        return None
    pit = ctx.pitchers
    pt = ctx.pitch_types
    pool = pt[pt["qualified"] & (pt["pool_key"] == row["pool_key"])].copy()
    pool = pool.join(pit[["fb_velo", "fb_ivb", "fb_hb"]], on="pitcher")
    pool["sep_velo"] = pool["fb_velo"] - pool["velo"]
    pool["sep_ivb"] = pool["fb_ivb"] - pool["ivb"]
    pool["sep_hb"] = pool["hb_arm"] - pool["fb_hb"]
    me = pit.loc[pid]
    mine = {"velo": row["velo"], "ivb": row["ivb"], "hb_arm": row["hb_arm"], "spin": row["spin"],
            "sep_velo": me["fb_velo"] - row["velo"], "sep_ivb": me["fb_ivb"] - row["ivb"], "sep_hb": row["hb_arm"] - me["fb_hb"]}
    top = pool[pool["g_stuff"] >= pool["g_stuff"].quantile(0.75)]
    labels = {"velo": ("velo", "mph"), "ivb": ("induced vertical break", "in"), "hb_arm": ("arm-side break", "in"),
              "spin": ("spin", "rpm"), "sep_velo": ("velo gap off the fastball", "mph"),
              "sep_ivb": ("vertical separation from the fastball", "in"), "sep_hb": ("horizontal separation from the fastball", "in")}
    if row["fam"] in ("FF", "SI", "FC"):
        for k in ("sep_velo", "sep_ivb", "sep_hb"):
            labels.pop(k)
    best = None
    for k in labels:
        sd = pool[k].std()
        if not np.isfinite(sd) or sd == 0 or not np.isfinite(mine[k]):
            continue
        gap = (top[k].mean() - mine[k]) / sd
        if best is None or abs(gap) > abs(best[1]):
            best = (k, gap)
    if best is None or abs(best[1]) < 0.4:
        return None
    k, gap = best
    word, unit = labels[k]
    fmt = "{:.0f}" if unit == "rpm" else "{:.1f}"
    mv, pv = mine[k], top[k].mean()
    if k.startswith("sep_") and np.sign(mv) == np.sign(pv):
        mv, pv = abs(mv), abs(pv)
    return {"pitch": row["pitch_type"], "name": row["name"], "grade": row["g_stuff"], "trait": word,
            "mine": fmt.format(mv), "peer": fmt.format(pv), "unit": unit,
            "direction": "more" if pv > mv else "less", "fam": row["fam"], "n_top": len(top)}


def _splits(df: pd.DataFrame) -> dict[str, Any]:
    """Platoon and times-through-order lines computed from his Statcast PAs."""
    pa = df[df["pa_end"]]
    ev = pa["events"].fillna("")
    woba = pd.to_numeric(pa["woba_value"], errors="coerce")

    def line(mask_pa: pd.Series, mask_p: pd.Series) -> dict[str, float]:
        p, g = pa[mask_pa], df[mask_p]
        n = len(p)
        sw, oz = g["swing"].sum(), (~g["in_zone"]).sum()
        return {
            "pa": n, "woba": woba[mask_pa].mean() if n else np.nan, "xwoba": p["xwoba_pa"].mean() if n else np.nan,
            "k": ev[mask_pa].str.startswith("strikeout").mean() if n else np.nan,
            "bb": ev[mask_pa].isin(["walk", "intent_walk"]).mean() if n else np.nan,
            "hr": int(ev[mask_pa].eq("home_run").sum()),
            "whiff": g["whiff"].sum() / sw if sw else np.nan, "chase": g["o_swing"].sum() / oz if oz else np.nan,
        }

    rows = {f"vs {s}HH": line(pa["stand"] == s, df["stand"] == s) for s in ("L", "R")}
    tto = df["n_thruorder_pitcher"].clip(upper=3)
    tto_pa = pa["n_thruorder_pitcher"].clip(upper=3)
    for k, lab in ((1, "1st time"), (2, "2nd time"), (3, "3rd+ time")):
        rows[lab] = line(tto_pa == k, tto == k)
    return rows


def build_pitcher_data(ctx: LeagueContext, pid: int, models: dict[str, Any]) -> dict[str, Any]:
    pit = ctx.pitchers
    if pid not in pit.index:
        raise ValueError(f"No {ctx.season} regular-season pitches for pitcher {pid}")
    row = pit.loc[pid]
    df = player_pitches(ctx, pitcher=pid)
    ars = _arsenal(ctx, pid, df)
    arsenal = ars["pitch_type"].tolist()
    stints = il_stints(ctx.data_dir, ctx.season, pid)
    plan = pd.DataFrame()
    if models.get("situational") is not None:
        try:
            plan = pitcher_count_plan(models["situational"], _raw_for_models(ctx, pid), data_dir=ctx.data_dir, season=ctx.season)
        except Exception:
            log.exception("Count plan failed for %s", pid)
    opt = None
    if models.get("outcome") is not None:
        try:
            opt = optimizer_suggestion(models["outcome"], _raw_for_models(ctx, pid))
        except Exception:
            log.exception("Optimizer failed for %s", pid)
    hand = str(row["p_throws"])
    data = {
        "kind": "pitcher", "id": pid, "name": ctx.name(pid), "hand": hand, "hand_word": f"{hand}HP",
        "role": str(row["role"]), "team": current_team(ctx.data_dir, ctx.season, pid) or str(row.get("fg_team") or ""),
        "age": row.get("fg_age") if np.isfinite(row.get("fg_age", np.nan)) else row.get("age"),
        "row": row, "df": df, "arsenal": ars, "stints": stints, "plan": plan, "optimizer": opt,
        "counts": _count_strategy(df, plan, arsenal), "seq": _sequencing(df, arsenal), "tunnel": _tunnel(df),
        "trend": _trends(df, row.get("fb_fam"), stints), "comps": _comps(ctx, pid),
        "shape_note": _shape_note(ctx, ars, pid), "ctx": ctx, "splits": _splits(df),
        "signature": {r["pitch_type"]: _signature_rank(ctx, r) for _, r in ars.iterrows() if r["n"] >= MIN_PITCH_TYPE_N},
    }
    data["findings"] = narrative.pitcher_findings(data)
    return data


def _raw_for_models(ctx: LeagueContext, pid: int) -> pd.DataFrame:
    from pitch_dataset.reports.context import _all_columns, read_regular_season
    from pitch_dataset.storage import pitch_path

    path = pitch_path(ctx.data_dir, season=ctx.season, league="mlb")
    return read_regular_season(path, columns=_all_columns(path), filters=[("pitcher", "==", int(pid))])


# ------------------------------------------------------------------ rendering


def _p(row: pd.Series, col: str) -> float | None:
    v = row.get(f"pct_{col}")
    return float(v) if v is not None and np.isfinite(v) else None


def _page1(d: dict[str, Any]) -> str:
    ctx: LeagueContext = d["ctx"]
    row = d["row"]
    age = f"Age {int(d['age'])}" if d.get("age") and np.isfinite(d["age"]) else ""
    role = {"SP": "Starter", "RP": "Reliever"}.get(d["role"], d["role"])
    meta = " · ".join(x for x in [d["team"], d["hand_word"], role, age, f"{int(row['n']):,} pitches", f"{int(row['games'])} G"] if x)
    rmeta = (f"<b>Pitcher evaluation</b><br>{ctx.season} regular season<br>Data through <b>{ctx.date_range[1]}</b>"
             f"<br>MLBAM {d['id']}")
    head = R.header(kind="Pitcher evaluation · R&D advance report", name=d["name"], meta=meta, rmeta=rmeta)
    ip = row.get("IP")
    line = R.statline([
        ("IP", S.num(ip, 1), None),
        ("ERA", S.num(row.get("ERA"), 2), _p(row, "ERA")),
        ("FIP", S.num(row.get("FIP"), 2), _p(row, "FIP")),
        ("xFIP", S.num(row.get("xFIP"), 2), _p(row, "xFIP")),
        ("xERA", S.num(row.get("xERA"), 2), _p(row, "xERA")),
        ("K%", S.pct(row.get("K%"), 1), _p(row, "K%")),
        ("BB%", S.pct(row.get("BB%"), 1), _p(row, "BB%")),
        ("K-BB%", S.pct(row.get("K-BB%"), 1), _p(row, "K-BB%")),
        ("CSW%", S.pct(row.get("csw_pct"), 1), _p(row, "csw_pct")),
        ("Whiff%", S.pct(row.get("whiff_pct"), 1), _p(row, "whiff_pct")),
        ("Chase%", S.pct(row.get("chase_pct"), 1), _p(row, "chase_pct")),
        ("FB velo", S.num(row.get("fb_velo"), 1), _p(row, "fb_velo")),
    ])
    pool_note = f"vs {int(ctx.pitchers['qualified'].sum())} pitchers ≥600 pitches"
    dur_note = ("IP/GS " + S.num(row.get("ip_per_gs"), 1)) if d["role"] == "SP" else ("G " + S.num(row.get("G"), 0))
    grades = R.grades_panel("20–80 grades", [
        ("Stuff", row.get("g_stuff"), 100 * row.get("p_stuff", np.nan), f"{S.signed(row.get('stuff100'), 2)} RV/100"),
        ("Command", row.get("g_command"), 100 * row.get("p_command", np.nan), f"BB {S.pct(row.get('BB%'), 1)}"),
        ("Bat-missing", row.get("g_miss"), 100 * row.get("p_miss", np.nan), f"Whiff {S.pct(row.get('whiff_pct'), 0)}"),
        ("Contact mgmt", row.get("g_contact"), 100 * row.get("p_contact", np.nan), f"xwOBAcon {S.rate3(row.get('xwoba_con'))}"),
        ("Durability", row.get("g_durability"), None, dur_note),
    ], note=pool_note + ("" if row.get("qualified") else " · <span class=flag>below qualifying sample</span>"))
    top = (f'<div class="row"><div class="col" style="flex:1.75">{R.bottom_line(d["bullets"])}</div>'
           f'<div class="col" style="flex:1">{grades}</div></div>')
    table = _arsenal_table(d)
    mv, heat = _movement(d), _heatmaps(d)
    body = (f'<div class="row"><div class="col" style="flex:1.04">{mv}</div>'
            f'<div class="col" style="flex:1">{heat}</div></div>')
    foot = R.footer(kind="Pitcher evaluation", through=ctx.date_range[1], page=1, pages=2,
                    notes="Grades: league percentile → 20–80 (50 avg, 10 = 1 SD); method on p.2. "
                          + R.color_legend())
    return head + line + top + table + body + foot


def _arsenal_table(d: dict[str, Any]) -> str:
    ars = d["arsenal"]
    rows = []
    for r in ars.itertuples():
        small = r.n < MIN_PITCH_TYPE_N
        sw = f'<span class="sw" style="background:{S.PITCH_COLORS.get(r.pitch_type, S.MUTED)}"></span>'
        hb_txt = S.num(r.hb, 1)
        cells = [
            f'<td class="l">{sw}<b>{S.esc(r.name)}</b> <span class="muted">{r.pitch_type}</span></td>',
            f"<td>{int(r.n)}</td>", f"<td><b>{S.pct(r.usage)}</b></td>", f"<td>{S.pct(r.vsL)}</td>", f"<td>{S.pct(r.vsR)}</td>",
            f'<td class="sep">{S.pct(r.b_First)}</td>', f"<td>{S.pct(r.b_Ahead)}</td>", f"<td>{S.pct(r.b_Behind)}</td>",
            f"<td>{S.pct(r.b_2K)}</td>",
            R.pct_cell(S.num(r.velo, 1), r.pct_velo).replace("<td", '<td class="sep"', 1),
            R.pct_cell(S.num(r.spin, 0), r.pct_spin), f"<td>{S.num(r.ivb, 1)}</td>", f"<td>{hb_txt}</td>",
            f"<td>{S.num(r.ext, 1)}</td>",
            R.pct_cell(S.pct(r.whiff_pct), r.pct_whiff_pct).replace("<td", '<td class="sep"', 1),
            R.pct_cell(S.pct(r.chase_pct), r.pct_chase_pct), f"<td>{S.pct(r.csw_pct)}</td>",
            R.pct_cell(S.rate3(r.xwoba), r.pct_xwoba), R.pct_cell(S.signed(r.rvn100, 1), r.pct_rvn100),
            f'<td class="c sep">{S.grade_chip(r.g_stuff)}</td>', f'<td class="c">{S.grade_chip(r.g_results)}</td>',
            f'<td class="c">{S.grade_chip(r.g_command)}</td>',
        ]
        rows.append(f'<tr class="{"small" if small else ""}">{"".join(cells)}</tr>')
    head = (
        '<thead><tr class="grp"><th></th><th colspan="4">Usage</th><th colspan="4" class="sep">Usage by count</th>'
        '<th colspan="5" class="sep">Shape</th><th colspan="5" class="sep">Results</th><th colspan="3" class="sep">Grades (20–80)</th></tr>'
        '<tr><th class="l">Pitch</th><th>n</th><th>All</th><th>vL</th><th>vR</th><th class="sep">0-0</th><th>Ahd</th>'
        '<th>Bhd</th><th>2K</th><th class="sep">Velo</th><th>Spin</th><th>IVB</th><th>HB</th><th>Ext</th>'
        '<th class="sep">Whiff</th><th>Chase</th><th>CSW</th><th>xwOBA</th><th>RV/100</th>'
        '<th class="c sep">Stuff</th><th class="c">Res</th><th class="c">Cmd</th></tr></thead>'
    )
    best = ars.sort_values("g_stuff", ascending=False).iloc[0] if len(ars) else None
    title = "Arsenal"
    if best is not None and np.isfinite(best["g_stuff"]):
        title = (f"Arsenal — {best['name'].lower()} is the best pitch by shape "
                 f"({display_grade(best['g_stuff'])} Stuff, {grade_word(best['g_stuff'])})")
    sub = ("Velo mph · spin rpm · IVB/HB inches, catcher view (HB + = toward 1B) · Ext ft · Whiff per swing · Chase = swing "
           "% outside zone · xwOBA per PA ended · RV/100 = count-neutral run value per 100 pitches, + = good for pitcher · "
           f"cells tinted by percentile within pitch type & hand · grey rows: n < {MIN_PITCH_TYPE_N}")
    return R.section(title, sub, f'<table class="tbl">{head}<tbody>{"".join(rows)}</tbody></table>', tag="Arsenal")


def _movement(d: dict[str, Any]) -> str:
    ctx, df, ars = d["ctx"], d["df"], d["arsenal"]
    pts = df[df["pitch_type"].isin(ars["pitch_type"])]
    pts = pts.sample(frac=1.0, random_state=3)
    pts = pts[pts.groupby("pitch_type").cumcount() < 110]
    refs = {}
    for r in ars.itertuples():
        ref = ctx.movement.get((r.fam, d["hand"]))
        if ref and r.usage >= 0.05:
            refs[r.pitch_type] = ref
    svg = S.movement_plot(pts[["pitch_type", "hb", "ivb"]], ars[["pitch_type", "hb", "ivb"]], refs, w=318, h=296)
    lead = ars.iloc[0]
    ref = ctx.movement.get((lead["fam"], d["hand"]))
    sub = ("Dots = individual pitches (≤110 per type); large markers = his averages; dashed ellipses = league 1-SD shape "
           f"for the same pitch type from {d['hand_word']}s. Inches, catcher view.")
    title = "Movement profile"
    if ref:
        divv = lead["ivb"] - ref["mean"][1]
        title = (f"Movement — {lead['name'].lower()} carries {abs(divv):.1f} in {'more' if divv > 0 else 'less'} "
                 f"IVB than the average {d['hand_word']} {FAMILY_NAMES.get(lead['fam'], lead['fam']).lower()}")
    return R.section(title, sub, f'<div class="svgwrap">{svg}</div>', tag="Shape")


def _heatmaps(d: dict[str, Any]) -> str:
    df, ars = d["df"], d["arsenal"]
    top = ars.head(3)
    cells = ['<div class="hd"></div><div class="hd">vs LHH</div><div class="hd">vs RHH</div>']
    best_txt = None
    for r in top.itertuples():
        if ((df["pitch_type"] == r.pitch_type).groupby(df["stand"]).sum() >= 15).sum() == 0:
            continue
        cells.append(f'<div class="hd" style="writing-mode:vertical-rl;transform:rotate(180deg);text-align:center">'
                     f'<span style="color:{S.PITCH_COLORS.get(r.pitch_type, S.MUTED)};font-weight:700">{S.esc(r.name)}</span></div>')
        for stand in ("L", "R"):
            g = df[(df["pitch_type"] == r.pitch_type) & (df["stand"] == stand)]
            top_z, bot_z = float(g["sz_top"].mean() or 3.4), float(g["sz_bot"].mean() or 1.6)
            sub = f"n={len(g)}"
            if len(g) >= 30:
                shadow = g["shadow"].mean()
                heart = g["heart"].mean()
                sub = f"n={len(g)} · edge {shadow * 100:.0f}% · heart {heart * 100:.0f}%"
            cells.append(S.location_heatmap(g["plate_x"].to_numpy(float), g["plate_z"].to_numpy(float),
                                            sz_top=top_z, sz_bot=bot_z, w=124, h=120, sub=sub)
                         if len(g) >= 15 else f'<div class="muted" style="font-size:6.5pt;padding:30px 8px">n={len(g)} — too few</div>')
    lead = top.iloc[0] if len(top) else None
    if lead is not None:
        sub_l = df[(df["pitch_type"] == lead["pitch_type"])]
        up = (sub_l["plate_z"] > sub_l["sz_top"] - (sub_l["sz_top"] - sub_l["sz_bot"]) / 3).mean()
        best_txt = f"Location — {up * 100:.0f}% of his {lead['name'].lower()}s finish in the upper third or above"
    grid = f'<div class="mini-grid" style="grid-template-columns:12px 1fr 1fr">{"".join(cells)}</div>'
    sub = ("Smoothed density of pitch locations (catcher view; box = average rule-book zone, thirds marked). "
           "Darker = more frequent (frequency, not quality) <span class='sq' style='display:inline-block;width:40px;height:5px;"
           "background:linear-gradient(90deg,#fafbfc,#1d3f6e)'></span> · edge = within ±3 in of the zone border.")
    return R.section(best_txt or "Location", sub, grid, tag="Location")


def _splits_section(d: dict[str, Any]) -> str:
    sp, ctx, row = d["splits"], d["ctx"], d["row"]
    lg_xw = ctx.league.get("xwoba_pa", 0.315)
    head = ("<thead><tr><th class='l'>Split</th><th>PA</th><th>wOBA</th><th>xwOBA</th><th>K%</th><th>BB%</th>"
            "<th>HR</th><th>Whiff</th><th>Chase</th></tr></thead>")
    rows = []
    for lab, s in sp.items():
        if s["pa"] == 0:
            continue
        small = s["pa"] < 60
        p = None if small or not np.isfinite(s["xwoba"]) else float(np.clip(0.5 - (s["xwoba"] - lg_xw) / 0.12, 0, 1))
        sep = " style='border-top:1px solid #cfd5dd'" if lab == "1st time" else ""
        rows.append(f"<tr class='{'small' if small else ''}'{sep}><td class='l'><b>{lab}</b></td><td>{s['pa']}</td>"
                    f"<td>{S.rate3(s['woba'])}</td>{R.pct_cell(S.rate3(s['xwoba']), None if p is None else 100 * p)}"
                    f"<td>{S.pct(s['k'], 1)}</td><td>{S.pct(s['bb'], 1)}</td><td>{s['hr']}</td>"
                    f"<td>{S.pct(s['whiff'])}</td><td>{S.pct(s['chase'])}</td></tr>")
    l, r = sp["vs LHH"], sp["vs RHH"]
    title = "Splits"
    if np.isfinite(l["xwoba"]) and np.isfinite(r["xwoba"]):
        worse = "LHH" if l["xwoba"] > r["xwoba"] else "RHH"
        gap = abs(l["xwoba"] - r["xwoba"]) * 1000
        title = (f"Splits — {'even platoon profile' if gap < 25 else f'{worse} do more damage'} "
                 f"({gap:.0f}-pt xwOBA gap)")
    vh = row.get("velo_hold")
    extra = (f"Velo hold: primary FB {S.signed(vh, 1)} mph on pitches 76+ vs 1–25. " if np.isfinite(vh) else "")
    sub = (f"Statcast PAs, regular season. xwOBA tint vs league {S.rate3(lg_xw)} (red = better for him). "
           f"Times through order use the batter's PA count vs this pitcher in the game. {extra}Grey rows: &lt; 60 PA.")
    return R.section(title, sub, f"<table class='tbl'>{head}<tbody>{''.join(rows)}</tbody></table>", tag="Splits")


def _page2(d: dict[str, Any]) -> str:
    ctx: LeagueContext = d["ctx"]
    head = R.header(kind="Pitcher evaluation · continued", name=d["name"], meta="",
                    rmeta=f"{d['team']} · {d['hand_word']} · {ctx.season} · through <b>{ctx.date_range[1]}</b>", compact=True)
    counts = _count_section(d)
    seq = _sequence_section(d)
    trends = _trend_section(d)
    comps = _comps_section(d)
    dev = _dev_section(d)
    splits = _splits_section(d)
    body = (counts
            + f'<div class="row"><div class="col" style="flex:1">{seq}</div><div class="col" style="flex:1.05">{trends}</div></div>'
            + f'<div class="row"><div class="col" style="flex:1">{splits}</div><div class="col" style="flex:1.05">{comps}</div></div>'
            + dev)
    method = R.method_block([
        ("Grades", ("each scale is a z-score composite converted to a percentile within the qualified pool, then "
         "50 + 10·Φ⁻¹(p), clipped 20–80 and shown to the nearest 5. Pitch grades are within the same pitch type and "
         "throwing hand (≥100 pitches). Stuff = a gradient-boosted model of expected, count-neutral run value from "
         "velo, movement, spin, extension, release, arm angle and separation from the primary fastball (no location or "
         f"results; held-out pitch-type correlation r={ctx.stuff_meta.get('holdout_pitchtype_corr', float('nan')):.2f}). "
         "Results = whiff%, CSW%, xwOBA. Command = edge%, waste%, heart% (pitch) and BB%, edge, zone, first-strike (overall). "
         "Durability = IP/start, pitches/game, late-game velo hold (relievers: G, IP).")),
        ("Models", ("count plan = situational pitch-type model (2026, generic league-average hitter, medium leverage, "
         "2nd time through); location/tunneling from Statcast trajectory fits at a 23.8 ft decision point; usage "
         "suggestion = constrained arsenal optimizer (±15 pts/pitch). Model gaps are small effects — treat as direction.")),
        ("Caveats", ("single season, regular season only; small-sample cells greyed; xwOBA ignores park and defense; "
         "IL dates from MLB transactions (retroactive dates honored).")),
    ])
    foot = R.footer(kind="Pitcher evaluation", through=ctx.date_range[1], page=2, pages=2,
                    notes="Counts are balls-strikes before the pitch. " + R.color_legend())
    return head + body + method + foot


def _count_section(d: dict[str, Any]) -> str:
    grid = d["counts"]["grid"]
    tables = []
    for stand in ("L", "R"):
        hdr = "".join(f"<th class='c'>{c}</th>" for c in COUNTS)
        r1, r2, r3 = [], [], []
        for c in COUNTS:
            cell = grid.get((stand, c))
            if not cell:
                r1.append("<td class='c muted'>–</td>")
                r2.append("<td class='c muted'>–</td>")
                r3.append("<td class='c muted'>–</td>")
                continue
            small = cell["n"] < 25
            # Predictability tint: ≥70% one pitch = strong signal for hitters (bad for pitcher).
            pred = cell["share"]
            bg = R.tint(max(0.0, 1 - (pred - 0.35) / 0.5)) if not small else "transparent"
            col = S.PITCH_COLORS.get(cell["top"], S.MUTED)
            r1.append(f"<td class='c' style='background:{bg}'><b style='color:{col}'>{cell['top']}</b> {pred * 100:.0f}%"
                      f"<div class='muted' style='font-size:5.6pt'>n={cell['n']}</div></td>")
            if cell.get("model"):
                mc = S.PITCH_COLORS.get(cell["model"], S.MUTED)
                same = cell["model"] == cell["top"]
                r2.append(f"<td class='c'><b style='color:{mc}'>{cell['model']}</b>{'' if same else ' ◆'}</td>")
                dlt = cell.get("delta", np.nan)
                r3.append(f"<td class='c' style='background:{R.tint(max(0.0, 1 - dlt / 0.03)) if np.isfinite(dlt) else 'transparent'}'>"
                          f"{S.num(1000 * dlt, 0) if np.isfinite(dlt) else '–'}</td>")
            else:
                r2.append("<td class='c muted'>–</td>")
                r3.append("<td class='c muted'>–</td>")
        tables.append(
            f"<table class='tbl' style='margin-bottom:3px'><thead><tr><th class='l'>vs {stand}HH</th>{hdr}</tr></thead><tbody>"
            f"<tr><td class='l'>Throws most</td>{''.join(r1)}</tr><tr><td class='l'>Model pick</td>{''.join(r2)}</tr>"
            f"<tr><td class='l'>Mix gap (pts)</td>{''.join(r3)}</tr></tbody></table>"
        )
    pred = d["counts"]["predictable"]
    gaps = d["counts"]["gaps"]
    side = []
    if pred:
        side.append("<div class='kicker' style='margin-bottom:1px'>Most predictable</div>")
        for p in pred[:3]:
            side.append(f"<div>{p['count']} vs {p['stand']}HH · <b>{p['share'] * 100:.0f}% {p['pitch_type']}</b> "
                        f"<span class='muted'>n={p['n']}</span></div>")
    if gaps:
        side.append("<div class='kicker' style='margin:4px 0 1px'>Largest model gaps</div>")
        for g in gaps[:3]:
            side.append(f"<div>{g['count']} vs {g['stand']}HH · {g['top']} {g['share'] * 100:.0f}% → <b>{g['model']}</b> "
                        f"<span class='muted'>{S.rate3(g['top_xw'])}→{S.rate3(g['model_xw'])}</span></div>")
    title = "Count strategy"
    if pred:
        p = pred[0]
        title = (f"Count strategy — most predictable in {p['count']} vs {p['stand']}HH "
                 f"({p['share'] * 100:.0f}% {pitch_label(p['pitch_type']).lower()})")
    sub = ("Throws most = his most-used pitch in each count (tint: red = mixed, blue = ≥70% one pitch, i.e. predictable). "
           "Model pick = lowest expected xwOBA from the situational model vs a league-average hitter (◆ = differs). "
           "Mix gap = his actual mix's model xwOBA minus the model pick's, in points (.001); blue = larger opportunity.")
    body = (f'<div class="row" style="margin-top:0"><div class="col" style="flex:3.1">{"".join(tables)}</div>'
            f'<div class="col note" style="flex:1.05;font-size:6.8pt;line-height:1.45">{"".join(side)}</div></div>')
    return R.section(title, sub, body, tag="Counts", style="margin-top:6px")


def _sequence_section(d: dict[str, Any]) -> str:
    seq, tun = d["seq"], d["tunnel"]
    trans = seq["trans"]
    arsenal = [pt for pt in trans.index if seq["n_prev"].get(pt, 0) >= 30][:6]
    hdr = "".join(f"<th class='c'><span style='color:{S.PITCH_COLORS.get(pt, S.MUTED)}'>{pt}</span></th>" for pt in arsenal)
    rows = []
    for a in arsenal:
        tds = "".join(
            f"<td class='c' style='background:{S.seq_color(trans.loc[a, b] * 1.3)};color:{S.text_on(S.seq_color(trans.loc[a, b] * 1.3))}'>"
            f"{trans.loc[a, b] * 100:.0f}</td>" for b in arsenal
        )
        rows.append(f"<tr><td class='l'><b style='color:{S.PITCH_COLORS.get(a, S.MUTED)}'>{a}</b> "
                    f"<span class='muted'>n={int(seq['n_prev'].get(a, 0))}</span></td>{tds}</tr>")
    table = f"<table class='tbl'><thead><tr><th class='l'>After ↓ / next →</th>{hdr}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    notes = []
    for w in seq["whiff_after"][:2]:
        notes.append(f"{pitch_label(w['next'])} after {w['prev']}: <b>{w['whiff'] * 100:.0f}% whiff</b> vs "
                     f"{w['base'] * 100:.0f}% overall ({w['swings']} swings)")
    title = "Sequencing"
    if tun and tun.get("best"):
        b = tun["best"]
        notes.insert(0, f"Best tunnel: <b>{b['a']}/{b['b']}</b> — {b['dp_in']:.1f} in apart at the decision point, "
                        f"{b['plate_in']:.1f} in apart at the plate ({b['ratio']:.1f}× late separation; release {b['release_in']:.1f} in apart)")
        title = f"Sequencing — {b['a']}/{b['b']} is the best tunnel pair ({b['ratio']:.1f}× separation after the decision point)"
    sub = "Share (%) of next pitch within the same PA, by previous pitch. Tunnel = mean trajectories 23.8 ft from the plate vs at the plate."
    return R.section(title, sub, table + f"<div class='note' style='margin-top:4px'>{'<br>'.join(notes)}</div>", tag="Sequence")


def _trend_section(d: dict[str, Any]) -> str:
    tr = d["trend"]
    games = tr["games"]
    ctx = d["ctx"]
    lo, hi = pd.Timestamp(ctx.date_range[0]), pd.Timestamp(ctx.date_range[1])
    flags = {f["key"]: f for f in tr["flags"]}
    cells = []
    for key, label, unit, _thr, fmt in TREND_SPECS:
        if key not in games:
            continue
        f = flags.get(key)
        base = float(games.iloc[:-5][key].median()) if len(games) > 8 else float(games[key].median())
        cap = f"{label} ({unit})"
        if f:
            cap += f" <span class='flag'>⚑ {S.signed(f['delta'], 2 if unit == 'ft' else (0 if unit == 'rpm' else 1))} last 5</span>"
        chart = S.trend_chart(games["date"], games[key], w=178, h=118, fmt=fmt, stints=d["stints"], baseline=base,
                              flag_from=f["since"] if f else None, date_range=(lo, hi))
        cells.append(f"<div><div style='font-size:6.6pt;font-weight:600'>{cap}</div>{chart}</div>")
    title = "Trends — stable through the season"
    if tr["flags"]:
        f = tr["flags"][0]
        title = (f"Trends — {f['label'][0].lower() + f['label'][1:]} {'down' if f['delta'] < 0 else 'up'} "
                 f"{abs(f['delta']):{'.2f' if f['unit'] == 'ft' else ('.0f' if f['unit'] == 'rpm' else '.1f')}} {f['unit']} over his last 5 games")
    stint_txt = "; ".join(
        f"{R.fmt_date(s['start'])}–{R.fmt_date(s['end']) if s.get('end') is not None else 'season end'}"
        + (f" ({S.esc(s['reason'][:40])})" if s.get("reason") else "")
        for s in d["stints"]
    )
    sub = ("Per game (dots), 3-game rolling mean (line), dashed = baseline before last 5 games; ⚑ shaded = flagged window "
           "(≥1 mph, 75 rpm or 0.2 ft). " + (f"Grey = IL: {stint_txt}." if stint_txt else "No IL stints."))
    return R.section(title, sub, f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:3px 8px'>{''.join(cells)}</div>", tag="Trends")


def _comps_section(d: dict[str, Any]) -> str:
    comps = d["comps"]
    rows = "".join(
        f"<div class='comp'><span class='nm'>{S.esc(c['name'])} <span class='muted'>{S.esc(c['team'])}</span> "
        f"{S.grade_chip(c['stuff'])}</span><span><span class='simbar'><span style='width:{c['sim'] * 100:.0f}%'></span></span>"
        f"<span class='muted' style='font-size:6.3pt'>{c['sim'] * 100:.0f}% similar</span></span>"
        f"<span class='d'>{S.esc(c['note'])}</span></div>"
        for c in comps
    )
    title = f"Comps — closest arsenal profile: {comps[0]['name']}" if comps else "Comps"
    sub = ("Nearest neighbors among qualified pitchers on pitch mix, primary-FB velo/IVB/HB, arm angle, breaking-ball shape "
           "and separation, whiff% and zone% (standardized, weighted). Chip = comp's Stuff grade.")
    return R.section(title, sub, rows, tag="Comps")


def _dev_section(d: dict[str, Any]) -> str:
    notes = []
    opt = d["optimizer"]
    if opt:
        for seg in opt["segments"][:2]:
            ch = [c for c in seg["changes"] if abs(c[3]) >= 0.03][:3]
            if not ch:
                continue
            txt = ", ".join(f"{pt} {cur * 100:.0f}→{rec * 100:.0f}%" for pt, cur, rec, _ in ch)
            notes.append(f"<b>{seg['segment']}:</b> {txt} (model xwOBA {S.signed(1000 * seg['delta_xwoba'], 0)} pts, n={seg['n']})")
    sn = d["shape_note"]
    if sn:
        notes.append(
            f"<b>Shape:</b> his {sn['name'].lower()} grades {display_grade(sn['grade'])} Stuff. Top-quartile {d['hand_word']} "
            f"{FAMILY_NAMES.get(sn['fam'], '').lower()}s average {sn['peer']} {sn['unit']} of {sn['trait']} vs his "
            f"{sn['mine']} — the largest gap; worth a look in pitch design, not a prescription.")
    pil = d["trend"].get("post_il")
    if pil:
        notes.append(f"<b>Since IL return ({R.fmt_date(pil['end'])}):</b> FB {pil['post']:.1f} mph vs {pil['pre']:.1f} before "
                     f"({S.signed(pil['post'] - pil['pre'], 1)}, {pil['n_post']} games).")
    if not notes:
        notes.append("No usage or shape change clears the model's noise threshold.")
    title = "Development notes — usage direction from the arsenal optimizer"
    sub = ("Constrained optimizer on the outcome model (each pitch ±15 pts, 3–55% bounds). Expected gains are small and "
           "model-dependent: hypotheses for the pitching staff, not prescriptions.")
    return R.section(title, sub, "<div class='note'>" + "<br>".join(notes) + "</div>", tag="Develop")


def render_pitcher_html(d: dict[str, Any], *, screen_links: list[tuple[str, str]] | None = None) -> str:
    d["bullets"] = narrative.select(d["findings"])
    return R.document(f"{d['name']} — Pitcher evaluation ({d['ctx'].season})", [_page1(d), _page2(d)], screen_links=screen_links)
