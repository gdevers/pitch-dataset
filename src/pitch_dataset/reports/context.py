"""League context for player reports: regular-season pitches, league tables, and a Stuff model.

Everything a report compares a player against lives here: per pitcher × pitch type shape and
results, per pitcher and per batter season tables, league movement references, and the pitch-
shape "Stuff" model. Only aggregates are cached (``data/cache``); a report pulls its player's
pitch rows from the parquet on demand (:func:`player_pitches`).

Conventions:

* Regular season only (``game_type == "R"``).
* Run values: ``delta_pitcher_run_exp`` (pitcher perspective, + is good for the pitcher) and
  ``delta_run_exp`` (batter perspective). "Count-neutral" subtracts the league mean for the
  pre-pitch count so a pitch thrown in 3-0 is not penalized for the count it was thrown in.
* Movement: ``hb``/``ivb`` in inches, catcher's view (``pfx_x``/``pfx_z`` × 12); ``hb_arm``
  is mirrored so + is arm side for both hands.
* Edge distance ``edge_ft``: signed distance (ft) from the rule-book box border (17 in plate +
  ball radius, Statcast ``sz_top``/``sz_bot``); + inside. Heart > 0.25, shadow ±0.25,
  chase −0.25 to −0.75, waste < −0.75 (approximations of Savant's attack zones).
"""

from __future__ import annotations

import logging
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from pitch_dataset.spray import hc_to_feet, spray_angle
from pitch_dataset.storage import (
    chadwick_register_path,
    fangraphs_path,
    mlb_api_path,
    pitch_path,
)

log = logging.getLogger(__name__)

CACHE_VERSION = 6

PITCH_FAMILY = {
    "FF": "FF", "FA": "FF", "SI": "SI", "FC": "FC", "SL": "SL", "ST": "ST",
    "CU": "CU", "KC": "CU", "SV": "CU", "CS": "CU", "CH": "CH", "SC": "CH", "FS": "FS", "FO": "FS",
}
FAMILY_NAMES = {
    "FF": "Four-seam", "SI": "Sinker", "FC": "Cutter", "SL": "Slider", "ST": "Sweeper",
    "CU": "Curveball", "CH": "Changeup", "FS": "Splitter",
}
PITCH_NAMES = {
    **FAMILY_NAMES, "KC": "Knuckle curve", "SV": "Slurve", "CS": "Slow curve", "FO": "Forkball",
    "SC": "Screwball", "FA": "Fastball", "KN": "Knuckleball", "EP": "Eephus",
}
FAMILY_GROUP = {"FF": "FB", "SI": "FB", "FC": "FB", "SL": "BRK", "ST": "BRK", "CU": "BRK", "CH": "OFF", "FS": "OFF"}
GROUP_NAMES = {"FB": "Fastballs", "BRK": "Breaking", "OFF": "Offspeed"}
FAMILY_ORDER = ["FF", "SI", "FC", "SL", "ST", "CU", "CH", "FS"]

SWING = frozenset({
    "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play",
    "foul_bunt", "missed_bunt", "bunt_foul_tip",
})
WHIFF = frozenset({"swinging_strike", "swinging_strike_blocked", "missed_bunt"})
CALLED = frozenset({"called_strike"})

ZONE_HALF_W = 0.83
HEART_FT, CHASE_FT = 0.25, 0.75

MIN_PITCHER_PITCHES = 600  # qualified pitcher pool (~35 IP)
MIN_PITCH_TYPE_N = 100  # qualified pitcher × pitch type pool
MIN_BATTER_PITCHES = 1000  # qualified hitter pool (~250 PA)
MIN_GROUP_SEEN = 250  # hitter vs pitch group pool

_LOAD_COLS = [
    "pitch_type", "pitch_name", "game_date", "game_pk", "game_type", "pitcher", "batter",
    "player_name", "p_throws", "stand", "balls", "strikes", "outs_when_up", "inning",
    "at_bat_number", "pitch_number", "description", "events", "type", "zone", "plate_x",
    "plate_z", "sz_top", "sz_bot", "release_speed", "release_spin_rate", "release_extension",
    "release_pos_x", "release_pos_z", "pfx_x", "pfx_z", "arm_angle", "launch_speed",
    "launch_angle", "launch_speed_angle", "estimated_woba_using_speedangle",
    "estimated_ba_using_speedangle", "woba_value", "woba_denom", "bb_type", "hc_x", "hc_y",
    "hit_distance_sc", "delta_run_exp", "delta_pitcher_run_exp", "n_thruorder_pitcher",
    "home_team", "away_team", "inning_topbot", "age_pit", "age_bat",
]

STUFF_FEATURES = [
    "release_speed", "ivb", "hb_arm", "release_spin_rate", "release_extension",
    "release_pos_z", "rel_x_arm", "arm_angle", "d_velo", "d_ivb", "d_hb", "fam_code",
]

FG_TEAM_TO_MLB = {
    "SDP": "SD", "SFG": "SF", "KCR": "KC", "TBR": "TB", "WSN": "WSH", "CHW": "CWS", "ARI": "AZ",
    "OAK": "ATH",
}


def _strip_tags(v: Any) -> str:
    return "" if v is None or pd.isna(v) else re.sub(r"<[^>]+>", "", str(v))


def read_regular_season(path: Path, columns: list[str] | None = None, filters: list | None = None) -> pd.DataFrame:
    import pyarrow.parquet as pq

    have = set(pq.read_schema(path).names)
    cols = [c for c in (columns or _LOAD_COLS) if c in have]
    df = pd.read_parquet(path, columns=cols, filters=filters)
    if "game_type" in df.columns:
        df = df[df["game_type"] == "R"]
    return df.reset_index(drop=True)


def derive(df: pd.DataFrame, count_rv: pd.Series | None = None) -> pd.DataFrame:
    """Add swing/whiff/zone/edge/movement/run-value columns used by every report table."""
    out = df.copy()
    out["game_date"] = pd.to_datetime(out["game_date"])
    out["pitch_type"] = out["pitch_type"].fillna("").astype(str).str.upper()
    out["fam"] = out["pitch_type"].map(PITCH_FAMILY)
    out["grp"] = out["fam"].map(FAMILY_GROUP)
    desc = out["description"].fillna("").astype(str)
    out["swing"] = desc.isin(SWING)
    out["whiff"] = desc.isin(WHIFF)
    out["csw"] = out["whiff"] | desc.isin(CALLED)
    for c in ("balls", "strikes", "zone", "plate_x", "plate_z", "sz_top", "sz_bot", "pfx_x", "pfx_z",
              "launch_speed", "launch_angle", "release_pos_x", "delta_run_exp", "delta_pitcher_run_exp"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out["in_zone"] = out["zone"].between(1, 9)
    out["o_swing"] = out["swing"] & ~out["in_zone"]
    px, pz = out["plate_x"], out["plate_z"]
    top = out["sz_top"].fillna(3.4)
    bot = out["sz_bot"].fillna(1.6)
    edge = np.minimum(ZONE_HALF_W - px.abs(), np.minimum(pz - bot, top - pz))
    out["edge_ft"] = edge
    out["heart"] = edge > HEART_FT
    out["shadow"] = edge.between(-HEART_FT, HEART_FT)
    out["waste"] = edge < -CHASE_FT
    out["has_loc"] = px.notna() & pz.notna()
    rh = out["p_throws"].eq("R")
    out["hb"] = out["pfx_x"] * 12.0
    out["ivb"] = out["pfx_z"] * 12.0
    out["hb_arm"] = np.where(rh, -out["hb"], out["hb"])
    out["rel_x_arm"] = np.where(rh, -out["release_pos_x"], out["release_pos_x"])
    out["rv_p"] = out["delta_pitcher_run_exp"]
    out["rv_b"] = out["delta_run_exp"]
    key = out["balls"].fillna(0).astype(int).astype(str) + "-" + out["strikes"].fillna(0).astype(int).astype(str)
    out["count"] = key
    if count_rv is not None:
        out["rv_p_neutral"] = out["rv_p"] - key.map(count_rv).fillna(0.0)
    out["pa_end"] = pd.to_numeric(out["woba_denom"], errors="coerce").fillna(0).eq(1)
    xw_bip = pd.to_numeric(out["estimated_woba_using_speedangle"], errors="coerce")
    woba = pd.to_numeric(out["woba_value"], errors="coerce")
    out["bip"] = out["type"].eq("X")
    out["xwoba_pa"] = np.where(out["pa_end"], np.where(out["bip"] & xw_bip.notna(), xw_bip, woba), np.nan)
    out["xwoba_con"] = np.where(out["bip"], xw_bip, np.nan)
    out["xba_con"] = np.where(out["bip"], pd.to_numeric(out["estimated_ba_using_speedangle"], errors="coerce"), np.nan)
    ev = out["launch_speed"].where(out["bip"])
    out["ev"] = ev
    out["la"] = out["launch_angle"].where(out["bip"])
    out["barrel"] = pd.to_numeric(out["launch_speed_angle"], errors="coerce").eq(6) & out["bip"]
    out["hard"] = (ev >= 95) & out["bip"]
    out["sweet"] = out["la"].between(8, 32) & out["bip"]
    hx, hy = hc_to_feet(out["hc_x"], out["hc_y"])
    ang = spray_angle(hx, hy)
    out["spray"] = np.where(out["bip"], ang, np.nan)
    pull_sign = np.where(out["stand"].eq("L"), 1.0, -1.0)
    adj = out["spray"] * pull_sign  # + = pull side
    out["pull"] = (adj > 15) & out["bip"]
    out["oppo"] = (adj < -15) & out["bip"]
    out["air"] = out["bb_type"].isin(["fly_ball", "line_drive"]) & out["bip"]
    out["gb"] = out["bb_type"].eq("ground_ball") & out["bip"]
    out["pull_air"] = out["pull"] & out["air"]
    out["x_ft"], out["y_ft"] = hx, hy
    return out


def add_game_pitch_counts(df: pd.DataFrame) -> pd.DataFrame:
    order = df.sort_values(["pitcher", "game_pk", "at_bat_number", "pitch_number"])
    n = order.groupby(["pitcher", "game_pk"]).cumcount() + 1
    df = df.copy()
    df["game_pitch_no"] = n.reindex(df.index)
    return df


def primary_fastballs(df: pd.DataFrame) -> pd.DataFrame:
    """Per pitcher primary fastball (most-thrown FF/SI, else FC) mean velo / IVB / arm-side HB."""
    fb = df[df["fam"].isin(["FF", "SI", "FC"])]
    counts = fb.groupby(["pitcher", "fam"]).size().rename("n").reset_index()
    counts["rank_key"] = counts["n"] * np.where(counts["fam"].eq("FC"), 0.5, 1.0)
    best = counts.sort_values("rank_key", ascending=False).drop_duplicates("pitcher")
    sel = fb.merge(best[["pitcher", "fam"]], on=["pitcher", "fam"])
    return sel.groupby("pitcher").agg(
        fb_fam=("fam", "first"), fb_velo=("release_speed", "mean"), fb_ivb=("ivb", "mean"), fb_hb=("hb_arm", "mean")
    )


def add_stuff_features(df: pd.DataFrame, fb: pd.DataFrame) -> pd.DataFrame:
    out = df.join(fb, on="pitcher")
    out["d_velo"] = out["release_speed"] - out["fb_velo"]
    out["d_ivb"] = out["ivb"] - out["fb_ivb"]
    out["d_hb"] = out["hb_arm"] - out["fb_hb"]
    out["fam_code"] = out["fam"].map({f: i for i, f in enumerate(FAMILY_ORDER)}).astype(float)
    return out


def add_expected_rv(df: pd.DataFrame) -> pd.DataFrame:
    """``xrv``: count-neutral pitcher RV with balls in play replaced by their EV × LA bin mean.

    Removes defense / sequencing / BABIP luck from the Stuff target while keeping whiffs,
    called strikes, balls and contact quality.
    """
    out = df.copy()
    ev_bin = np.floor(out["launch_speed"] / 3.0)
    la_bin = np.floor(out["launch_angle"] / 4.0)
    key = ev_bin.astype("Int64").astype(str) + "|" + la_bin.astype("Int64").astype(str)
    bip = out["bip"] & ev_bin.notna() & la_bin.notna()
    bin_mean = out.loc[bip, "rv_p_neutral"].groupby(key[bip]).mean()
    out["xrv"] = np.where(bip, key.map(bin_mean), out["rv_p_neutral"])
    return out


def train_stuff_model(df: pd.DataFrame) -> tuple[HistGradientBoostingRegressor, dict[str, Any]]:
    """Pitch shape → expected count-neutral pitcher RV per pitch. No location, batter, or count."""
    frame = df[df["fam"].notna() & df["xrv"].notna() & df["release_speed"].notna()]
    rng = np.random.default_rng(7)
    games = frame["game_pk"].unique()
    test_games = set(rng.choice(games, size=len(games) // 5, replace=False))
    is_test = frame["game_pk"].isin(test_games).to_numpy()
    X = frame[STUFF_FEATURES].astype(float)
    y = frame["xrv"].astype(float)
    model = HistGradientBoostingRegressor(
        max_iter=250, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=400,
        l2_regularization=1.0, random_state=7, categorical_features=[STUFF_FEATURES.index("fam_code")],
    )
    model.fit(X[~is_test], y[~is_test])
    pred = model.predict(X[is_test])
    test = frame.loc[is_test, ["pitcher", "pitch_type"]].assign(pred=pred, y=y[is_test].to_numpy())
    agg = test.groupby(["pitcher", "pitch_type"]).agg(n=("y", "size"), pred=("pred", "mean"), y=("y", "mean"))
    agg = agg[agg["n"] >= 100]
    # Out-of-sample: does training-split Stuff predict held-out games' actual run value?
    corr = float(np.corrcoef(agg["pred"], agg["y"])[0, 1]) if len(agg) > 10 else float("nan")
    model.fit(X, y)
    return model, {"n_train": len(frame), "holdout_pitchtype_corr": corr, "holdout_groups": len(agg)}


def _rate(num: pd.Series, den: pd.Series) -> pd.Series:
    return num / den.where(den > 0)


def pitch_type_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per pitcher × pitch type: usage, shape, results, command proxies, Stuff."""
    g = df.groupby(["pitcher", "pitch_type"])
    t = g.agg(
        n=("pitch_type", "size"), fam=("fam", "first"), p_throws=("p_throws", "first"),
        velo=("release_speed", "mean"), spin=("release_spin_rate", "mean"), ivb=("ivb", "mean"),
        hb=("hb", "mean"), hb_arm=("hb_arm", "mean"), ext=("release_extension", "mean"),
        rel_z=("release_pos_z", "mean"), arm_angle=("arm_angle", "mean"),
        swings=("swing", "sum"), whiffs=("whiff", "sum"), csw_n=("csw", "sum"),
        o_n=("in_zone", lambda s: (~s).sum()), o_sw=("o_swing", "sum"), z_n=("in_zone", "sum"),
        heart_n=("heart", "sum"), shadow_n=("shadow", "sum"), waste_n=("waste", "sum"),
        loc_n=("has_loc", "sum"), pa=("pa_end", "sum"), xw_sum=("xwoba_pa", "sum"),
        bip=("bip", "sum"), xwcon_sum=("xwoba_con", "sum"), rv=("rv_p", "sum"),
        rvn=("rv_p_neutral", "sum"), stuff=("stuff_pred", "mean"),
    ).reset_index()
    tot = t.groupby("pitcher")["n"].transform("sum")
    t["usage"] = t["n"] / tot
    t["whiff_pct"] = _rate(t["whiffs"], t["swings"])
    t["csw_pct"] = t["csw_n"] / t["n"]
    t["chase_pct"] = _rate(t["o_sw"], t["o_n"])
    t["zone_pct"] = t["z_n"] / t["n"]
    t["heart_pct"] = _rate(t["heart_n"], t["loc_n"])
    t["shadow_pct"] = _rate(t["shadow_n"], t["loc_n"])
    t["waste_pct"] = _rate(t["waste_n"], t["loc_n"])
    t["xwoba"] = _rate(t["xw_sum"], t["pa"])
    t["xwoba_con"] = _rate(t["xwcon_sum"], t["bip"])
    t["rv100"] = 100 * t["rv"] / t["n"]
    t["rvn100"] = 100 * t["rvn"] / t["n"]
    t["stuff100"] = 100 * t["stuff"]
    return t


def pitcher_table(df: pd.DataFrame, pt: pd.DataFrame, fg: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("pitcher")
    t = g.agg(
        n=("pitch_type", "size"), p_throws=("p_throws", lambda s: s.mode().iloc[0]),
        name=("player_name", "first"), games=("game_pk", "nunique"),
        swings=("swing", "sum"), whiffs=("whiff", "sum"), csw_n=("csw", "sum"),
        o_sw=("o_swing", "sum"), z_n=("in_zone", "sum"), heart_n=("heart", "sum"),
        shadow_n=("shadow", "sum"), waste_n=("waste", "sum"), loc_n=("has_loc", "sum"),
        bip=("bip", "sum"), xwcon_sum=("xwoba_con", "sum"), barrels=("barrel", "sum"),
        gb_n=("gb", "sum"), age=("age_pit", "max"),
    )
    t["o_n"] = t["n"] - t["z_n"]
    t["whiff_pct"] = _rate(t["whiffs"], t["swings"])
    t["csw_pct"] = t["csw_n"] / t["n"]
    t["chase_pct"] = _rate(t["o_sw"], t["o_n"])
    t["zone_pct"] = t["z_n"] / t["n"]
    t["heart_pct"] = _rate(t["heart_n"], t["loc_n"])
    t["shadow_pct"] = _rate(t["shadow_n"], t["loc_n"])
    t["waste_pct"] = _rate(t["waste_n"], t["loc_n"])
    t["xwoba_con"] = _rate(t["xwcon_sum"], t["bip"])
    t["barrel_pct"] = _rate(t["barrels"], t["bip"])
    t["gb_pct"] = _rate(t["gb_n"], t["bip"])
    first = df[df["pitch_number"] == 1]
    t["fstrike_pct"] = first.groupby("pitcher")["type"].apply(lambda s: s.isin(["S", "X"]).mean())
    w = pt.assign(w=pt["n"] * pt["stuff100"]).groupby("pitcher")[["w", "n"]].sum()
    t["stuff100"] = w["w"] / w["n"]
    fbs = primary_fastballs(df)
    t = t.join(fbs)
    # Velo hold: primary fastball velo on pitches 76+ minus pitches 1–25 (same game set).
    fbp = df[df["fam"] == df["pitcher"].map(fbs["fb_fam"])]
    early = fbp[fbp["game_pitch_no"] <= 25].groupby("pitcher")["release_speed"].mean()
    late = fbp[fbp["game_pitch_no"] >= 76].groupby("pitcher")["release_speed"].agg(["mean", "size"])
    t["velo_hold"] = (late["mean"] - early).where(late["size"] >= 40)
    gp = df.groupby(["pitcher", "game_pk"]).size().groupby("pitcher").mean()
    t["pitches_per_g"] = gp
    tto = df[df["pa_end"]].groupby(["pitcher", df["n_thruorder_pitcher"].clip(upper=3)])["xwoba_pa"].agg(["mean", "size"])
    tto = tto.unstack()
    for k in (1, 3):
        if ("mean", k) in tto.columns:
            t[f"tto{k}_xwoba"] = tto[("mean", k)].where(tto[("size", k)] >= 60)
    fgc = _fg_pitching(fg)
    t = t.join(fgc, how="left").join(platoon_splits(df, "pitcher", "stand"))
    t["role"] = np.where((t["GS"].fillna(0) / t["G"].replace(0, np.nan)).fillna(0) >= 0.5, "SP", "RP")
    t["ip_per_gs"] = t["IP"] / t["GS"].where(t["GS"] > 0)
    return t


def _fg_pitching(fg: pd.DataFrame) -> pd.DataFrame:
    if fg is None or fg.empty:
        return pd.DataFrame()
    cols = ["xMLBAMID", "Name", "Team", "Age", "IP", "GS", "G", "W", "L", "SV", "ERA", "FIP", "xFIP",
            "xERA", "SIERA", "K%", "BB%", "K-BB%", "WAR", "TBF", "HR/9", "GB%", "Pitches"]
    f = fg[[c for c in cols if c in fg.columns]].copy()
    f["Name"] = f["Name"].map(_strip_tags)
    f["Team"] = f["Team"].map(_strip_tags)
    f = f.dropna(subset=["xMLBAMID"])
    f["xMLBAMID"] = f["xMLBAMID"].astype(int)
    f = f.sort_values("IP", ascending=False).drop_duplicates("xMLBAMID")
    return f.set_index("xMLBAMID").rename(columns={"Name": "fg_name", "Team": "fg_team", "Age": "fg_age",
                                                   "GB%": "fg_gb", "Pitches": "fg_pitches"})


def batter_table(df: pd.DataFrame, fg: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("batter")
    t = g.agg(
        n=("pitch_type", "size"), stand=("stand", lambda s: s.mode().iloc[0]),
        games=("game_pk", "nunique"), swings=("swing", "sum"), whiffs=("whiff", "sum"),
        z_n=("in_zone", "sum"), o_sw=("o_swing", "sum"), bip=("bip", "sum"),
        ev_mean=("ev", "mean"), ev_max=("ev", "max"), ev90=("ev", lambda s: s.quantile(0.9)),
        la_mean=("la", "mean"), barrels=("barrel", "sum"), hard_n=("hard", "sum"),
        sweet_n=("sweet", "sum"), pull_n=("pull", "sum"), oppo_n=("oppo", "sum"),
        air_n=("air", "sum"), gb_n=("gb", "sum"), pull_air_n=("pull_air", "sum"),
        xwcon_sum=("xwoba_con", "sum"), age=("age_bat", "max"),
    )
    z_sw = df[df["in_zone"]].groupby("batter")["swing"].sum()
    t["o_n"] = t["n"] - t["z_n"]
    t["swing_pct"] = t["swings"] / t["n"]
    t["z_swing_pct"] = _rate(z_sw.reindex(t.index).fillna(0), t["z_n"])
    t["chase_pct"] = _rate(t["o_sw"], t["o_n"])
    t["contact_pct"] = 1 - _rate(t["whiffs"], t["swings"])
    t["whiff_pct"] = _rate(t["whiffs"], t["swings"])
    t["barrel_pct"] = _rate(t["barrels"], t["bip"])
    t["hard_pct"] = _rate(t["hard_n"], t["bip"])
    t["sweet_pct"] = _rate(t["sweet_n"], t["bip"])
    t["pull_pct"] = _rate(t["pull_n"], t["bip"])
    t["oppo_pct"] = _rate(t["oppo_n"], t["bip"])
    t["gb_pct"] = _rate(t["gb_n"], t["bip"])
    t["air_pct"] = _rate(t["air_n"], t["bip"])
    t["pull_air_pct"] = _rate(t["pull_air_n"], t["bip"])
    t["xwoba_con"] = _rate(t["xwcon_sum"], t["bip"])
    t["sw_minus_ch"] = t["z_swing_pct"] - t["chase_pct"]
    first = df[df["pitch_number"] == 1]
    t["fp_swing_pct"] = first.groupby("batter")["swing"].mean()
    two = df[df["strikes"] == 2]
    t["chase_2k"] = _rate(two.groupby("batter")["o_swing"].sum(), (~two["in_zone"]).groupby(two["batter"]).sum())
    for grp in ("FB", "BRK", "OFF"):
        s = df[df["grp"] == grp].groupby("batter")
        t[f"seen_{grp}"] = s.size()
        t[f"rv100_{grp}"] = 100 * s["rv_b"].mean()
        t[f"whiff_{grp}"] = _rate(s["whiff"].sum(), s["swing"].sum())
        t[f"xwcon_{grp}"] = _rate(s["xwoba_con"].sum(), s["bip"].sum())
    t = t.join(_fg_batting(fg), how="left")
    return t.join(platoon_splits(df, "batter", "p_throws"))


def platoon_splits(df: pd.DataFrame, who: str, side_col: str) -> pd.DataFrame:
    """PA, wOBA and xwOBA by opponent hand from Statcast PA-ending pitches (``_vs_l`` / ``_vs_r``)."""
    pa = df[df["pa_end"]]
    woba = pd.to_numeric(pa["woba_value"], errors="coerce")
    g = pa.assign(woba=woba).groupby([who, side_col]).agg(
        PA=("woba", "size"), wOBA=("woba", "mean"), xwOBA=("xwoba_pa", "mean")
    ).unstack(side_col)
    g.columns = [f"{m}_vs_{h.lower()}" for m, h in g.columns]
    return g


def _fg_batting(fg: pd.DataFrame) -> pd.DataFrame:
    if fg is None or fg.empty:
        return pd.DataFrame()
    cols = ["xMLBAMID", "Name", "Team", "Age", "G", "PA", "HR", "SB", "AVG", "OBP", "SLG", "OPS",
            "ISO", "wOBA", "xwOBA", "xAVG", "xSLG", "wRC+", "K%", "BB%", "Spd", "WAR", "BsR", "Bats"]
    f = fg[[c for c in cols if c in fg.columns]].copy()
    f["Name"] = f["Name"].map(_strip_tags)
    f["Team"] = f["Team"].map(_strip_tags)
    f = f.dropna(subset=["xMLBAMID"])
    f["xMLBAMID"] = f["xMLBAMID"].astype(int)
    f = f.sort_values("PA", ascending=False).drop_duplicates("xMLBAMID")
    return f.set_index("xMLBAMID").rename(columns={"Name": "fg_name", "Team": "fg_team", "Age": "fg_age"})


def pitch_bands(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Velocity / movement / type bands used in the hitter report (masks may overlap)."""
    fam, v, ivb = df["fam"], df["release_speed"], df["ivb"]
    ff = fam.eq("FF")
    return {
        "FF 96+ mph": ff & (v >= 96),
        "FF 93–95.9": ff & v.between(93, 95.95),
        "FF < 93": ff & (v < 93),
        "FF ride ≥ 18 in": ff & (ivb >= 18),
        "Sinker": fam.eq("SI"),
        "Cutter": fam.eq("FC"),
        "Slider": fam.eq("SL"),
        "Sweeper": fam.eq("ST"),
        "Curveball": fam.eq("CU"),
        "Changeup": fam.eq("CH"),
        "Splitter": fam.eq("FS"),
    }


def band_stats(df: pd.DataFrame, mask: pd.Series) -> dict[str, float]:
    g = df[mask]
    sw = g["swing"].sum()
    out_z = (~g["in_zone"]).sum()
    return {
        "n": float(len(g)), "swing": g["swing"].mean() if len(g) else np.nan,
        "whiff": g["whiff"].sum() / sw if sw else np.nan,
        "chase": g["o_swing"].sum() / out_z if out_z else np.nan,
        "xwcon": g["xwoba_con"].mean() if g["bip"].any() else np.nan,
        "xwoba": g["xwoba_pa"].mean() if g["pa_end"].any() else np.nan,
        "rv100": 100 * g["rv_b"].mean() if len(g) else np.nan, "bip": float(g["bip"].sum()),
        "pa": float(g["pa_end"].sum()),
    }


def zone_group_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per (pitch group, batter-relative zone): swing%, whiff/swing, xwOBA on contact."""
    from pitch_dataset.location import assign_location_zones

    z = assign_location_zones(df["plate_x"], df["plate_z"], df["stand"], df["sz_top"], df["sz_bot"])["loc_zone"]
    d = df.assign(loc_zone=z.to_numpy())
    g = d[d["grp"].notna() & d["loc_zone"].notna()].groupby(["grp", "loc_zone"])
    t = g.agg(n=("swing", "size"), swing=("swing", "mean"), sw=("swing", "sum"), wh=("whiff", "sum"),
              xwcon=("xwoba_con", "mean"))
    t["whiff"] = t["wh"] / t["sw"].where(t["sw"] > 0)
    return t[["n", "swing", "whiff", "xwcon"]]


def count_table(df: pd.DataFrame) -> pd.DataFrame:
    """Swing%, chase%, whiff/swing, xwOBA on contact by pre-pitch count."""
    g = df.groupby("count")
    t = pd.DataFrame({
        "n": g.size(), "swing": g["swing"].mean(),
        "chase": g["o_swing"].sum() / g["in_zone"].apply(lambda s: (~s).sum()).replace(0, np.nan),
        "whiff": g["whiff"].sum() / g["swing"].sum().replace(0, np.nan),
        "xwcon": g["xwoba_con"].mean(),
    })
    return t


def movement_reference(df: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    """League mean + covariance of (HB, IVB) per pitch family × hand (catcher view, inches)."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    sub = df[df["fam"].notna() & df["hb"].notna() & df["ivb"].notna()]
    for (fam, hand), g in sub.groupby(["fam", "p_throws"]):
        if len(g) < 500:
            continue
        xy = g[["hb", "ivb"]].to_numpy(float)
        out[(fam, hand)] = {
            "mean": xy.mean(axis=0).tolist(), "cov": np.cov(xy.T).tolist(), "n": len(g),
            "velo": float(g["release_speed"].mean()), "spin": float(g["release_spin_rate"].mean()),
        }
    return out


@dataclass
class LeagueContext:
    season: int
    data_dir: Path
    date_range: tuple[str, str]
    n_pitches: int
    count_rv: pd.Series
    pitch_types: pd.DataFrame  # pitcher × pitch type
    pitchers: pd.DataFrame
    batters: pd.DataFrame
    movement: dict[tuple[str, str], dict[str, Any]]
    league: dict[str, float]
    stuff_model: Any
    stuff_meta: dict[str, Any]
    fb_ref: pd.DataFrame  # primary fastball reference per pitcher (for Stuff features)
    names: dict[int, str] = field(default_factory=dict)
    attack_pitchers: dict[str, pd.DataFrame] = field(default_factory=dict)  # hand → prepared sample
    grades: dict[str, Any] = field(default_factory=dict)
    bands: dict[str, dict[str, float]] = field(default_factory=dict)
    zone_groups: pd.DataFrame | None = None
    counts: pd.DataFrame | None = None  # league swing / chase / whiff by count

    def name(self, pid: int) -> str:
        return self.names.get(int(pid), str(pid))


def _register_names(data_dir: Path, ids: set[int]) -> dict[int, str]:
    path = chadwick_register_path(data_dir)
    if not path.exists():
        return {}
    reg = pd.read_parquet(path)
    reg = reg[reg["key_mlbam"].isin(ids)]
    return {int(k): f"{f} {lname}" for k, f, lname in zip(reg["key_mlbam"], reg["name_first"], reg["name_last"], strict=True)}


def _source_paths(data_dir: Path, season: int) -> list[Path]:
    return [
        pitch_path(data_dir, season=season, league="mlb"),
        fangraphs_path(data_dir, season=season, stat_type="pitching"),
        fangraphs_path(data_dir, season=season, stat_type="batting"),
    ]


def _cache_path(data_dir: Path, season: int) -> Path:
    return data_dir / "cache" / f"report_context_{season}.pkl"


def _attack_sample(df_raw: pd.DataFrame, hand: str, data_dir: Path, season: int, n_games: int = 160) -> pd.DataFrame:
    """Prepared league sample of one pitcher hand: a 'league-average arsenal' for hitter plans."""
    from pitch_dataset.situational import prepare_situational_pitches

    games = df_raw["game_pk"].drop_duplicates().sample(n=n_games, random_state=11).tolist()
    path = pitch_path(data_dir, season=season, league="mlb")
    sample = read_regular_season(path, columns=_all_columns(path), filters=[("game_pk", "in", games)])
    sample = sample[sample["p_throws"] == hand]
    return prepare_situational_pitches(sample, data_dir=data_dir, season=season)


def build_league_context(data_dir: Path | str = "data", season: int = 2026, *, use_cache: bool = True) -> LeagueContext:
    data_dir = Path(data_dir)
    cache = _cache_path(data_dir, season)
    stamp = [CACHE_VERSION] + [p.stat().st_mtime if p.exists() else 0 for p in _source_paths(data_dir, season)]
    if use_cache and cache.exists():
        try:
            with cache.open("rb") as fh:
                saved_stamp, ctx = pickle.load(fh)
            if saved_stamp == stamp:
                return ctx
        except Exception:  # noqa: BLE001 - stale / incompatible cache is simply rebuilt
            log.info("Report context cache unreadable; rebuilding")

    path = pitch_path(data_dir, season=season, league="mlb")
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Pull it first: `uv run pitch-dataset pull --season {season}`")
    log.info("Building report league context from %s", path)
    raw = read_regular_season(path, columns=None)
    count_key = raw["balls"].astype(int).astype(str) + "-" + raw["strikes"].astype(int).astype(str)
    count_rv = pd.to_numeric(raw["delta_pitcher_run_exp"], errors="coerce").groupby(count_key).mean()
    df = derive(raw, count_rv=count_rv)
    df = add_game_pitch_counts(df)
    fb = primary_fastballs(df)
    df = add_stuff_features(df, fb)
    df = add_expected_rv(df)
    stuff_model, stuff_meta = train_stuff_model(df)
    ok = df["fam"].notna() & df["release_speed"].notna()
    df["stuff_pred"] = np.nan
    df.loc[ok, "stuff_pred"] = stuff_model.predict(df.loc[ok, STUFF_FEATURES].astype(float))

    def _fg(kind: str) -> pd.DataFrame | None:
        p = fangraphs_path(data_dir, season=season, stat_type=kind)
        return pd.read_parquet(p) if p.exists() else None

    pt = pitch_type_table(df)
    pit = pitcher_table(df, pt, _fg("pitching"))
    bat = batter_table(df, _fg("batting"))
    names = _register_names(data_dir, set(pit.index) | set(bat.index))
    league = {
        "whiff_pct": float(df["whiff"].sum() / df["swing"].sum()),
        "chase_pct": float(df["o_swing"].sum() / (~df["in_zone"]).sum()),
        "csw_pct": float(df["csw"].mean()),
        "zone_pct": float(df["in_zone"].mean()),
        "xwoba_con": float(df["xwoba_con"].mean()),
        "xwoba_pa": float(df["xwoba_pa"].mean()),
        "swing_pct": float(df["swing"].mean()),
        "z_swing_pct": float(df.loc[df["in_zone"], "swing"].mean()),
        "barrel_pct": float(df.loc[df["bip"], "barrel"].mean()),
        "hard_pct": float(df.loc[df["bip"], "hard"].mean()),
        "pull_air_pct": float(df.loc[df["bip"], "pull_air"].mean()),
        **{f"bip_{k}": float(df.loc[df["bip"], k].mean()) for k in ("pull", "oppo", "gb", "pull_air")},
        **{f"bb_{k}": float(df.loc[df["bip"], "bb_type"].eq(v).mean())
           for k, v in (("gb", "ground_ball"), ("ld", "line_drive"), ("fb", "fly_ball"), ("pu", "popup"))},
        "fp_swing_pct": float(df.loc[df["pitch_number"] == 1, "swing"].mean()),
        "chase_2k": float(df.loc[(df["strikes"] == 2) & ~df["in_zone"], "swing"].mean()),
    }
    dates = df["game_date"]
    ctx = LeagueContext(
        season=season, data_dir=data_dir,
        date_range=(str(dates.min().date()), str(dates.max().date())),
        n_pitches=len(df), count_rv=count_rv, pitch_types=pt, pitchers=pit, batters=bat,
        movement=movement_reference(df), league=league, stuff_model=stuff_model,
        stuff_meta=stuff_meta, fb_ref=fb, names=names,
        bands={k: band_stats(df, m) for k, m in pitch_bands(df).items()},
        zone_groups=zone_group_table(df), counts=count_table(df),
    )
    for hand in ("R", "L"):
        try:
            ctx.attack_pitchers[hand] = _attack_sample(raw, hand, data_dir, season)
        except Exception:
            log.exception("Could not build league %sHP sample for attack plans", hand)

    from pitch_dataset.reports.grades import apply_grades

    apply_grades(ctx)
    cache.parent.mkdir(parents=True, exist_ok=True)
    with cache.open("wb") as fh:
        pickle.dump((stamp, ctx), fh, protocol=pickle.HIGHEST_PROTOCOL)
    log.info("Report context: %d pitches, %d pitchers, %d batters", len(df), len(pit), len(bat))
    return ctx


def player_pitches(ctx: LeagueContext, *, pitcher: int | None = None, batter: int | None = None) -> pd.DataFrame:
    """All regular-season pitch rows for one player (full columns), derived + Stuff predictions."""
    path = pitch_path(ctx.data_dir, season=ctx.season, league="mlb")
    col, pid = ("pitcher", pitcher) if pitcher is not None else ("batter", batter)
    raw = read_regular_season(path, columns=_all_columns(path), filters=[(col, "==", int(pid))])
    df = derive(raw, count_rv=ctx.count_rv)
    df = add_game_pitch_counts(df)
    if pitcher is not None:
        df = add_stuff_features(df, ctx.fb_ref)
        ok = df["fam"].notna() & df["release_speed"].notna() & df["fb_velo"].notna()
        df["stuff_pred"] = np.nan
        if ok.any():
            df.loc[ok, "stuff_pred"] = ctx.stuff_model.predict(df.loc[ok, STUFF_FEATURES].astype(float))
    return df


def _all_columns(path: Path) -> list[str]:
    import pyarrow.parquet as pq

    return list(pq.read_schema(path).names)


def il_stints(data_dir: Path | str, season: int, player_id: int) -> list[dict[str, Any]]:
    """Injured-list placements (start, end or None, description) from MLB API transactions."""
    path = mlb_api_path(data_dir, season=season, kind="transactions")
    if not path.exists():
        return []
    tx = pd.read_parquet(path)
    tx = tx[tx["player_id"] == player_id].sort_values("date")
    desc = tx["description"].fillna("")
    stints: list[dict[str, Any]] = []
    for d, text in zip(tx["date"], desc, strict=True):
        low = text.lower()
        if "placed" in low and "injured list" in low:
            m = re.search(r"retroactive to ([A-Za-z]+ \d+, \d{4})", text)
            start = pd.to_datetime(m.group(1)) if m else pd.to_datetime(d)
            reason = text.split(".", 1)[1].strip().rstrip(".") if "." in text else ""
            stints.append({"start": start, "end": None, "reason": reason})
        elif "activated" in low and "injured list" in low and stints and stints[-1]["end"] is None:
            stints[-1]["end"] = pd.to_datetime(d)
    return stints


def current_team(data_dir: Path | str, season: int, player_id: int) -> str | None:
    path = mlb_api_path(data_dir, season=season, kind="rosters")
    if not path.exists():
        return None
    r = pd.read_parquet(path)
    r = r[r["player_id"] == player_id]
    return str(r["team_abbr"].iloc[0]) if not r.empty else None
