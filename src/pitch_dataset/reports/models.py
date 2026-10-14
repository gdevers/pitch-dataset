"""Model-backed report sections: count plans, hitter attack plans, arsenal optimizer.

Reuses the situational pitch-type model, the step-2 location model and the arsenal outcome
model exactly as ``recommend_pitch`` / ``optimize_pitcher`` do, but batches every count ×
batter-side context into one prediction call per report.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pitch_dataset.arsenal import (
    BATTER_PT_PRIOR_COLS,
    arsenal_pitch_types,
    batter_pitch_type_prior_table,
    context_row_features,
    pitcher_arsenal_means,
    primary_pitch_type,
)
from pitch_dataset.location import (
    add_location_columns,
    batter_zone_prior_table,
    score_locations,
)
from pitch_dataset.situational import (
    _build_context_row,
    _finalize_situational_features,
    prepare_situational_pitches,
)

log = logging.getLogger(__name__)

COUNTS = ["0-0", "1-0", "2-0", "3-0", "0-1", "1-1", "2-1", "3-1", "0-2", "1-2", "2-2", "3-2"]
BUCKETS = {
    "Even": ["0-0", "1-1", "2-2"],
    "Ahead": ["0-1", "0-2", "1-2"],
    "Behind": ["1-0", "2-0", "2-1", "3-1"],
    "Two-strike": ["0-2", "1-2", "2-2", "3-2"],
}
ATTACK_TYPES = ["FF", "SI", "FC", "SL", "ST", "CU", "CH", "FS"]


@lru_cache(maxsize=4)
def load_models(models_dir: str = "models") -> dict[str, Any]:
    from pitch_dataset.arsenal import load_outcome_model
    from pitch_dataset.location import load_location_model
    from pitch_dataset.situational import load_situational_model

    root = Path(models_dir)
    out: dict[str, Any] = {"situational": None, "location": None, "outcome": None}
    for key, fname, loader in (
        ("situational", "situational_model.joblib", load_situational_model),
        ("location", "situational_location_model.joblib", load_location_model),
        ("outcome", "outcome_model.joblib", load_outcome_model),
    ):
        path = root / fname
        if path.exists():
            try:
                out[key] = loader(path)
            except Exception:
                log.exception("Could not load %s", path)
    return out


def _features(model: Any, pitcher_df: pd.DataFrame, arsenal: list[str], *, count: str, stand: str,
              p_throws: str, batter_prior: float = 0.320, fg_woba: float = 0.320, fg_xwoba: float = 0.320,
              batter_pt_priors: pd.DataFrame | None = None, means: pd.DataFrame | None = None,
              primary: str | None = None) -> pd.DataFrame:
    balls, strikes = (int(v) for v in count.split("-"))
    ctx = _build_context_row(
        balls=balls, strikes=strikes, stand=stand, p_throws=p_throws, outs=1, runners_on=0,
        score_diff=0, leverage="medium", tto=2, batter_xwoba_prior=batter_prior, prev_pitch=None,
        fg_batter_woba_platoon=fg_woba, fg_batter_xwoba_platoon=fg_xwoba, pitcher_df=pitcher_df,
    )
    feat = context_row_features(
        ctx, arsenal, arsenal_means=means, primary_pitch=primary,
        batter_pt_priors=batter_pt_priors, extra_context_cols=BATTER_PT_PRIOR_COLS,
    )
    return _finalize_situational_features(feat, ctx, model)


def pitcher_count_plan(model: Any, raw: pd.DataFrame, *, data_dir: Path | str, season: int) -> pd.DataFrame:
    """Model xwOBA for every arsenal pitch × count × batter side vs a league-average hitter."""
    prepared = prepare_situational_pitches(raw, data_dir=data_dir, season=season)
    arsenal = [pt for pt in arsenal_pitch_types(prepared, min_n=25) if pt in model.pitch_types]
    if len(arsenal) < 2:
        return pd.DataFrame()
    p_throws = str(prepared["p_throws"].mode().iloc[0])
    means, primary = pitcher_arsenal_means(prepared), primary_pitch_type(prepared)
    frames, keys = [], []
    for stand in ("L", "R"):
        for count in COUNTS:
            frames.append(_features(model, prepared, arsenal, count=count, stand=stand, p_throws=p_throws,
                                    means=means, primary=primary))
            keys.append((stand, count))
    X = pd.concat(frames, ignore_index=True)
    xw, rv = model.predict_xwoba(X), model.predict_rv(X)
    rows = []
    for i, (stand, count) in enumerate(keys):
        for j, pt in enumerate(arsenal):
            k = i * len(arsenal) + j
            rows.append({"stand": stand, "count": count, "pitch_type": pt, "pred_xwoba": float(xw[k]), "pred_rv": float(rv[k])})
    return pd.DataFrame(rows)


def hitter_attack_plan(models: dict[str, Any], league_samples: dict[str, pd.DataFrame], raw: pd.DataFrame, *,
                       data_dir: Path | str, season: int) -> pd.DataFrame:
    """Best pitch type + zone per count bucket and pitcher hand vs this hitter (league-average arsenal)."""
    sit, loc = models.get("situational"), models.get("location")
    if sit is None or raw.empty:
        return pd.DataFrame()
    bprep = prepare_situational_pitches(raw, data_dir=data_dir, season=season)
    priors = batter_pitch_type_prior_table(bprep)
    order = bprep.sort_values([c for c in ("game_date", "game_pk", "at_bat_number", "pitch_number") if c in bprep])
    batter_prior = float(order["batter_xwoba_prior"].iloc[-1]) if len(order) else 0.320
    zone_priors = None
    if loc is not None:
        zone_priors = batter_zone_prior_table(add_location_columns(bprep), loc.league_zone)
    rows = []
    for hand, pdf in league_samples.items():
        if pdf is None or pdf.empty:
            continue
        vs = bprep[bprep["p_throws"] == hand]
        if len(vs) < 150:
            continue
        stand = str(vs["stand"].mode().iloc[0])
        fg_w = float(vs["fg_batter_woba_platoon"].median())
        fg_x = float(vs["fg_batter_xwoba_platoon"].median())
        counts = pdf["pitch_type"].value_counts()
        arsenal = [pt for pt in ATTACK_TYPES if pt in sit.pitch_types and counts.get(pt, 0) >= 200]
        means, primary = pitcher_arsenal_means(pdf), primary_pitch_type(pdf)
        for bucket, cts in BUCKETS.items():
            feats = [
                _features(sit, pdf, arsenal, count=c, stand=stand, p_throws=hand, batter_prior=batter_prior,
                          fg_woba=fg_w, fg_xwoba=fg_x, batter_pt_priors=priors, means=means, primary=primary)
                for c in cts
            ]
            X = pd.concat(feats, ignore_index=True)
            xw = sit.predict_xwoba(X).reshape(len(cts), len(arsenal)).mean(axis=0)
            order_idx = np.argsort(xw)
            best_pt = arsenal[int(order_idx[0])]
            entry = {
                "hand": hand, "stand": stand, "bucket": bucket, "pitch_type": best_pt,
                "pred_xwoba": float(xw[order_idx[0]]), "second": arsenal[int(order_idx[1])],
                "second_xwoba": float(xw[order_idx[1]]),
                "worst": arsenal[int(order_idx[-1])], "worst_xwoba": float(xw[order_idx[-1]]),
                "zone": None, "zone_whiff": np.nan, "zone_rv": np.nan,
            }
            if loc is not None and zone_priors is not None:
                agg: dict[str, list[tuple[float, float]]] = {}
                for f in feats:
                    scored = score_locations(loc, f, arsenal, zone_priors)[best_pt]
                    for s in scored:
                        agg.setdefault(s.zone, []).append((s.pred_rv, s.pred_whiff))
                zone_rank = sorted(agg.items(), key=lambda kv: np.mean([v[0] for v in kv[1]]))
                zid, vals = zone_rank[0]
                entry.update(zone=zid, zone_rv=float(np.mean([v[0] for v in vals])),
                             zone_whiff=float(np.mean([v[1] for v in vals])))
            rows.append(entry)
    return pd.DataFrame(rows)


def optimizer_suggestion(model: Any, raw: pd.DataFrame) -> dict[str, Any] | None:
    """Overall + platoon usage shifts from ``arsenal.optimize_pitcher`` (bounded ±15 pts/pitch)."""
    from pitch_dataset.arsenal import optimize_pitcher

    if model is None or raw.empty:
        return None
    try:
        rec = optimize_pitcher(raw, model, pitcher=int(raw["pitcher"].iloc[0]))
    except ValueError as exc:
        log.info("Optimizer skipped: %s", exc)
        return None
    segs = [s for s in rec.segments if "|" not in s.segment]
    return {
        "improvement_xwoba": rec.expected_improvement_xwoba,
        "improvement_rv": rec.expected_improvement_rv,
        "segments": [
            {"segment": s.segment, "n": s.n_pitches, "delta_xwoba": s.expected_improvement_xwoba,
             "changes": [(c.pitch_type, c.current_pct, c.recommended_pct, c.delta_pct) for c in s.changes]}
            for s in segs
        ],
    }
