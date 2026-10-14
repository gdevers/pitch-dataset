"""Templated "Bottom line" engine: rules → scored findings → ranked, capped bullets.

Every rule reads computed numbers from the report data and returns at most one ``Finding``
whose text embeds those numbers. No free-form generation: if a rule's threshold is not met it
stays silent. ``select`` ranks by notability score and keeps one finding per kind.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from pitch_dataset.reports.context import FAMILY_NAMES, PITCH_NAMES
from pitch_dataset.reports.grades import display_grade, grade_word
from pitch_dataset.reports.svg import pct, rate3, signed


@dataclass
class Finding:
    kind: str
    score: float
    text: str


def select(findings: list[Finding], cap: int = 5) -> list[str]:
    seen: set[str] = set()
    out = []
    for f in sorted(findings, key=lambda f: -f.score):
        if f.kind in seen or f.score <= 0:
            continue
        seen.add(f.kind)
        out.append(f.text)
        if len(out) == cap:
            break
    return out


def _ok(*vals: Any) -> bool:
    return all(v is not None and np.isfinite(v) for v in vals)


def _ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _pc(p: Any) -> str:
    return f"{_ordinal(int(np.clip(round(p), 1, 99)))} pct" if _ok(p) else "pct n/a"


def _name(pt: str) -> str:
    return PITCH_NAMES.get(pt, pt).lower()


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


# ------------------------------------------------------------------ pitcher rules


def _p_best_pitch(d: dict[str, Any]) -> Finding | None:
    ars = d["arsenal"]
    ars = ars[(ars["usage"] >= 0.08) & ars["g_stuff"].notna() & ars["g_results"].notna()]
    if ars.empty:
        return None
    combo = (ars["g_stuff"] + ars["g_results"]) / 2
    r = ars.loc[combo.idxmax()]
    g = (r["g_stuff"] + r["g_results"]) / 2
    if g < 55:
        return None
    sig = d["signature"].get(r["pitch_type"])
    sig_txt = ""
    if sig and sig["rank"] <= max(10, sig["of"] // 10):
        hand = d["hand_word"]
        sig_txt = (f"; {_ordinal(sig['rank'])}-most {sig['word']} of {sig['of']} {hand} "
                   f"{FAMILY_NAMES.get(r['fam'], r['fam']).lower()}s ({sig['value']} {sig['unit']})")
    lean = ""
    if r["b_2K"] >= r["usage"] + 0.05:
        lean = f"; already his 2-strike weapon ({pct(r['b_2K'])} of 2K pitches)"
    elif r["b_2K"] < r["usage"] + 0.02 and r["whiff_pct"] >= 0.33:
        lean = f"; only {pct(r['b_2K'])} of 2K pitches — room to lean on it to finish"
    text = (f"<b>Best pitch: {r['name'].lower()} ({display_grade(r['g_stuff'])} Stuff / "
            f"{display_grade(r['g_results'])} Results):</b> {pct(r['whiff_pct'], 1)} whiff, {rate3(r['xwoba'])} xwOBA, "
            f"{pct(r['usage'])} usage{sig_txt}{lean}.")
    return Finding("best_pitch", (g - 50) / 6, text)


def _p_underused(d: dict[str, Any]) -> Finding | None:
    ars = d["arsenal"]
    ars = ars[(ars["usage"] < 0.18) & (ars["n"] >= 150) & ars["g_results"].notna()]
    if ars.empty:
        return None
    r = ars.loc[ars["g_results"].idxmax()]
    if r["g_results"] < 60:
        return None
    return Finding("underused", (r["g_results"] - 55) / 7,
                   f"<b>Underused {r['name'].lower()} ({display_grade(r['g_results'])} Results):</b> "
                   f"{rate3(r['xwoba'])} xwOBA, {pct(r['whiff_pct'])} whiff, RV/100 {signed(r['rvn100'], 1)} on only "
                   f"{pct(r['usage'])} usage ({pct(r['vsL'])} vs LHH / {pct(r['vsR'])} vs RHH).")


def _p_run_prevention(d: dict[str, Any]) -> Finding | None:
    r = d["row"]
    era, xera, fip, p = r.get("ERA"), r.get("xERA"), r.get("FIP"), r.get("pct_xERA")
    if not _ok(era, xera, fip, p):
        return None
    word = ("Elite" if p >= 90 else "Strong" if p >= 70 else "Average" if p >= 30 else "Poor" if p < 10 else "Below-average")
    luck = ""
    if abs(era - xera) >= 0.6:
        luck = f"; ERA runs {abs(era - xera):.2f} {'above' if era > xera else 'below'} xERA — expect {'improvement' if era > xera else 'regression'}"
    return Finding("run_prev", max(abs(p - 50) / 18, abs(era - xera) / 0.5 if luck else 0, 0.3),
                   f"<b>{word} run prevention by xERA:</b> {era:.2f} ERA, {xera:.2f} xERA ({_pc(p)}), {fip:.2f} FIP, "
                   f"{pct(r.get('K-BB%'), 1)} K-BB{luck}.")


def _p_weak_pitch(d: dict[str, Any]) -> Finding | None:
    ars = d["arsenal"]
    ars = ars[(ars["usage"] >= 0.12) & ars["g_results"].notna() & (ars["n"] >= 150)]
    if ars.empty:
        return None
    r = ars.loc[ars["g_results"].idxmin()]
    if r["g_results"] > 43:
        return None
    text = (f"<b>{_cap(r['name'].lower())} is the hittable piece ({display_grade(r['g_results'])} Results):</b> "
            f"{rate3(r['xwoba'])} xwOBA and {pct(r['whiff_pct'])} whiff on {pct(r['usage'])} usage "
            f"({int(r['n'])} pitches; RV/100 {signed(r['rvn100'], 1)}).")
    return Finding("weak_pitch", (50 - r["g_results"]) / 7 + r["usage"] * 2, text)


def _p_trend(d: dict[str, Any]) -> Finding | None:
    flags = d["trend"]["flags"]
    if not flags:
        return None
    f = flags[0]
    thr = {"fb_velo": 1.0, "fb_spin": 75.0, "rel_z": 0.2, "ext": 0.2}[f["key"]]
    nd = 2 if f["unit"] == "ft" else (0 if f["unit"] == "rpm" else 1)
    il = ""
    if d["stints"]:
        s = d["stints"][-1]
        il = f"; IL from {s['start']:%b} {s['start'].day}" + (f" ({s['reason'].lower()[:45]})" if s.get("reason") else "")
    text = (f"<b>{f['label']} {'down' if f['delta'] < 0 else 'up'} {abs(f['delta']):.{nd}f} {f['unit']}</b> over his last 5 "
            f"games ({f['recent']:.{nd}f} vs {f['base']:.{nd}f} baseline){il} — verify health/mechanics before projecting.")
    return Finding("trend", 1.2 + abs(f["delta"]) / thr * 0.5, text)


def _p_predictable(d: dict[str, Any]) -> Finding | None:
    pred = d["counts"]["predictable"]
    if not pred or pred[0]["share"] < 0.62:
        return None
    p = pred[0]
    return Finding("predictable", (p["share"] - 0.5) * 6,
                   f"<b>Predictable in {p['count']} vs {p['stand']}HH:</b> {pct(p['share'])} {_name(p['pitch_type'])}s "
                   f"(n={p['n']}) — the count a hitter can sit on one pitch.")


def _p_model_gap(d: dict[str, Any]) -> Finding | None:
    gaps = d["counts"]["gaps"]
    if not gaps:
        return None
    g = gaps[0]
    diff = g["top_xw"] - g["model_xw"]
    if diff < 0.010:
        return None
    return Finding("model_gap", diff * 70,
                   f"<b>Opportunity in {g['count']} vs {g['stand']}HH:</b> throws {_name(g['top'])} {pct(g['share'])}; "
                   f"the situational model prefers {_name(g['model'])} ({rate3(g['model_xw'])} vs {rate3(g['top_xw'])} "
                   f"expected xwOBA, n={g['n']}).")


def _p_scale(key: str, label: str, detail: Callable[[Any], str]) -> Callable[[dict[str, Any]], Finding | None]:
    def rule(d: dict[str, Any]) -> Finding | None:
        g = d["row"].get(f"g_{key}")
        if not _ok(g) or abs(g - 50) < 10:
            return None
        return Finding(key, abs(g - 50) / 9, f"<b>{_cap(grade_word(g))} {label} ({display_grade(g)}):</b> {detail(d['row'])}.")

    return rule


def _p_platoon(d: dict[str, Any]) -> Finding | None:
    r = d["row"]
    wl, wr, nl, nr = r.get("wOBA_vs_l"), r.get("wOBA_vs_r"), r.get("PA_vs_l"), r.get("PA_vs_r")
    if not _ok(wl, wr, nl, nr) or min(nl, nr) < 120 or abs(wl - wr) < 0.045:
        return None
    worse = "LHH" if wl > wr else "RHH"
    return Finding("platoon", abs(wl - wr) * 22,
                   f"<b>Platoon gap:</b> {rate3(max(wl, wr))} wOBA allowed to {worse} vs {rate3(min(wl, wr))} to the other "
                   f"side ({abs(wl - wr) * 1000:.0f} pts; {int(nl)} / {int(nr)} PA vs L / R).")


def _p_tto(d: dict[str, Any]) -> Finding | None:
    r = d["row"]
    t1, t3 = r.get("tto1_xwoba"), r.get("tto3_xwoba")
    if d["role"] != "SP" or not _ok(t1, t3) or abs(t3 - t1) < 0.035:
        return None
    word = "fades" if t3 > t1 else "gets better"
    return Finding("tto", abs(t3 - t1) * 20,
                   f"<b>{_cap(word)} third time through:</b> xwOBA {rate3(t1)} first time vs {rate3(t3)} third+ "
                   f"({signed(1000 * (t3 - t1), 0)} pts).")


def _p_tunnel(d: dict[str, Any]) -> Finding | None:
    t = d.get("tunnel") or {}
    b = t.get("best")
    if not b or b["ratio"] < 2.2:
        return None
    return Finding("tunnel", 0.6 + min(b["ratio"], 6) / 10,
                   f"<b>Tunnel pair {b['a']}/{b['b']}:</b> {b['dp_in']:.1f} in apart at the decision point, "
                   f"{b['plate_in']:.1f} in at the plate ({b['ratio']:.1f}× late separation).")


PITCHER_RULES: list[Callable[[dict[str, Any]], Finding | None]] = [
    _p_best_pitch, _p_underused, _p_run_prevention, _p_weak_pitch, _p_trend, _p_predictable, _p_model_gap, _p_platoon, _p_tto, _p_tunnel,
    _p_scale("command", "command", lambda r: f"{pct(r.get('BB%'), 1)} BB ({_pc(r.get('pct_BB%'))}), "
             f"{pct(r.get('shadow_pct'))} of pitches on the edge, {pct(r.get('fstrike_pct'))} first-pitch strikes"),
    _p_scale("miss", "bat-missing", lambda r: f"{pct(r.get('K%'), 1)} K, {pct(r.get('whiff_pct'), 1)} whiff/swing "
             f"({_pc(r.get('pct_whiff_pct'))}), {pct(r.get('csw_pct'), 1)} CSW"),
    _p_scale("contact", "contact management", lambda r: f"{rate3(r.get('xwoba_con'))} xwOBA on contact, "
             f"{pct(r.get('barrel_pct'), 1)} barrels, {pct(r.get('gb_pct'))} grounders"),
    _p_scale("stuff", "overall stuff", lambda r: f"usage-weighted Stuff {signed(r.get('stuff100'), 2)} RV/100, primary FB "
             f"{r.get('fb_velo', float('nan')):.1f} mph ({_pc(r.get('pct_fb_velo'))})"),
]


def pitcher_findings(d: dict[str, Any]) -> list[Finding]:
    return [f for rule in PITCHER_RULES if (f := rule(d)) is not None]


# ------------------------------------------------------------------ hitter rules


def _h_scale(key: str, label: str, detail: Callable[[Any], str]) -> Callable[[dict[str, Any]], Finding | None]:
    def rule(d: dict[str, Any]) -> Finding | None:
        g = d["row"].get(f"g_{key}")
        if not _ok(g) or abs(g - 50) < 10:
            return None
        return Finding(key, abs(g - 50) / 9, f"<b>{_cap(grade_word(g))} {label} ({display_grade(g)}):</b> {detail(d['row'])}.")

    return rule


def _h_platoon(d: dict[str, Any]) -> Finding | None:
    r = d["row"]
    wl, wr, nl, nr = r.get("wOBA_vs_l"), r.get("wOBA_vs_r"), r.get("PA_vs_l"), r.get("PA_vs_r")
    if not _ok(wl, wr, nl, nr) or min(nl, nr) < 90 or abs(wl - wr) < 0.050:
        return None
    weak = "LHP" if wl < wr else "RHP"
    return Finding("platoon", abs(wl - wr) * 22,
                   f"<b>Platoon split — weaker vs {weak}:</b> {rate3(wl)} wOBA vs LHP, {rate3(wr)} vs RHP "
                   f"({abs(wl - wr) * 1000:.0f} pts; xwOBA {rate3(r.get('xwOBA_vs_l'))} / {rate3(r.get('xwOBA_vs_r'))}; "
                   f"{int(nl)} / {int(nr)} PA) — a matchup lever late in games.")


def _h_weak_band(d: dict[str, Any]) -> Finding | None:
    rows = [b for b in d["perf"] if b["n"] >= 80 and b["swings"] >= 30 and _ok(b["whiff"], b["lg_whiff"], b["rv100"])]
    if not rows:
        return None

    def badness(b: dict[str, Any]) -> float:
        return max((b["whiff"] - b["lg_whiff"]) / 0.05, (b["lg_rv100"] - b["rv100"]) / 1.0)

    b = max(rows, key=badness)
    if badness(b) < 1.0:
        return None
    whiff_txt = f"{pct(b['whiff'])} whiff/swing (league {pct(b['lg_whiff'])})"
    rv_txt = f"RV/100 {signed(b['rv100'], 1)} (league {signed(b['lg_rv100'], 1)})"
    lead = [whiff_txt, rv_txt] if b["whiff"] - b["lg_whiff"] >= 0.05 else [rv_txt, f"{rate3(b['xwcon'])} xwOBA on contact"]
    return Finding("weak_band", badness(b) * 0.8,
                   f"<b>Vulnerable vs {b['label']}:</b> {', '.join(lead)} (n={int(b['n'])} pitches).")


def _h_strong_band(d: dict[str, Any]) -> Finding | None:
    rows = [b for b in d["perf"] if b["bip"] >= 25 and _ok(b["rv100"], b["lg_rv100"])]
    if not rows:
        return None
    b = max(rows, key=lambda b: (b["rv100"] - b["lg_rv100"]) * np.sqrt(b["n"] / 300))
    gap = b["rv100"] - b["lg_rv100"]
    if gap < 1.2:
        return None
    return Finding("strong_band", gap / 2.2,
                   f"<b>Punishes {b['label'] if b['label'].startswith('FF') else b['label'].lower() + 's'}:</b> RV/100 {signed(b['rv100'], 1)} (league {signed(b['lg_rv100'], 1)}), "
                   f"{rate3(b['xwcon'])} xwOBA on contact (n={int(b['n'])}) — avoid in the zone.")


def _h_attack(d: dict[str, Any]) -> Finding | None:
    ap = d.get("attack")
    if ap is None or ap.empty:
        return None
    rows = ap[(ap["bucket"] == "Two-strike") & (ap["hand"] == "R")]
    if rows.empty:
        rows = ap[ap["bucket"] == "Two-strike"]
    if rows.empty:
        return None
    r = rows.iloc[0]
    zone_txt = ""
    if r.get("zone"):
        from pitch_dataset.location import zone_label

        zs = d.get("zone_support", {}).get((r["hand"], r["pitch_type"], r["zone"]))
        zone_txt = f", {zone_label(r['zone']).lower()}"
        if zs and zs["n"] >= 15:
            zone_txt += f" (he has {pct(zs['whiff'])} whiff there on {zs['grp_name'].lower()}, n={zs['n']})"
    return Finding("attack", 1.0,
                   f"<b>Two-strike plan vs {r['hand']}HP:</b> {_name(r['pitch_type'])}{zone_txt}; model xwOBA "
                   f"{rate3(r['pred_xwoba'])} vs {rate3(r['worst_xwoba'])} for {_name(r['worst'])}.")


def _h_alignment(d: dict[str, Any]) -> Finding | None:
    a = d.get("align")
    if not a or a["delta_per100"] < 1.5:
        return None
    from pitch_dataset.reports.defense import describe_moves

    gb = f"{pct(a['gb_pull'])} of grounders pulled; " if a.get("gb_pull") is not None else ""
    return Finding("alignment", a["delta_per100"] / 4,
                   f"<b>Positioning edge:</b> {gb}a shift-legal alignment converts {signed(a['delta_per100'], 1)} more outs "
                   f"per 100 balls in play than standard, cross-validated ({describe_moves(a['moves'][:2])}).")


def _h_trend(d: dict[str, Any]) -> Finding | None:
    flags = d["trend"]["flags"]
    if not flags:
        return None
    f = flags[0]
    return Finding("trend", 0.9 + abs(f["z"]) / 3,
                   f"<b>{f['label']} {'up' if f['delta'] > 0 else 'down'} lately:</b> {f['recent_txt']} over the last "
                   f"15 games vs {f['base_txt']} for the season.")


def _h_two_strike(d: dict[str, Any]) -> Finding | None:
    r = d["row"]
    c2, lg = r.get("chase_2k"), d["ctx"].league.get("chase_2k")
    if not _ok(c2, lg) or abs(c2 - lg) < 0.06:
        return None
    word = "expands" if c2 > lg else "protects well"
    return Finding("two_strike", abs(c2 - lg) * 8,
                   f"<b>Two-strike approach — {word}:</b> {pct(c2)} chase with two strikes (league {pct(lg)}).")


def _h_first_pitch(d: dict[str, Any]) -> Finding | None:
    r = d["row"]
    fp, lg = r.get("fp_swing_pct"), d["ctx"].league.get("fp_swing_pct")
    if not _ok(fp, lg) or abs(fp - lg) < 0.08:
        return None
    word = "Ambushes first pitches" if fp > lg else "Takes the first pitch"
    return Finding("first_pitch", abs(fp - lg) * 6, f"<b>{word}:</b> {pct(fp)} first-pitch swing rate (league {pct(lg)}).")


HITTER_RULES: list[Callable[[dict[str, Any]], Finding | None]] = [
    _h_platoon, _h_weak_band, _h_strong_band, _h_attack, _h_alignment, _h_trend, _h_two_strike, _h_first_pitch,
    _h_scale("power", "power", lambda r: f"{pct(r.get('barrel_pct'), 1)} barrels/BBE ({_pc(r.get('pct_barrel_pct'))}), "
             f"EV90 {r.get('ev90', float('nan')):.1f} mph, max {r.get('ev_max', float('nan')):.1f}, ISO {rate3(r.get('ISO'))}"),
    _h_scale("hit", "hit tool", lambda r: f"{pct(r.get('contact_pct'))} contact, xBA {rate3(r.get('xAVG'))}, "
             f"{pct(r.get('K%'), 1)} K"),
    _h_scale("discipline", "swing decisions", lambda r: f"{pct(r.get('chase_pct'), 1)} chase ({_pc(r.get('pct_chase_pct'))}), "
             f"{pct(r.get('z_swing_pct'))} zone swing, {pct(r.get('BB%'), 1)} BB"),
    _h_scale("pull_air", "pull-air profile", lambda r: f"{pct(r.get('pull_air_pct'), 1)} of batted balls pulled in the air "
             f"({_pc(r.get('pct_pull_air_pct'))})"),
]


def hitter_findings(d: dict[str, Any]) -> list[Finding]:
    return [f for rule in HITTER_RULES if (f := rule(d)) is not None]
