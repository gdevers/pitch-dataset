"""Counterfactual pitch-usage optimization under arsenal constraints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from pitch_dataset.arsenal.features import (
    CONTEXT_FEATURE_COLS,
    PITCH_ONEHOT_PREFIX,
    arsenal_pitch_types,
    prepare_pitches,
)
from pitch_dataset.arsenal.outcome import OutcomeModel


@dataclass
class UsageChange:
    pitch_type: str
    current_pct: float
    recommended_pct: float
    delta_pct: float


@dataclass
class SegmentRecommendation:
    segment: str
    n_pitches: int
    current_xwoba: float
    optimized_xwoba: float
    expected_improvement_xwoba: float
    current_rv: float
    optimized_rv: float
    expected_improvement_rv: float
    changes: list[UsageChange] = field(default_factory=list)


@dataclass
class PitcherRecommendation:
    pitcher_id: int
    pitcher_name: str
    n_pitches: int
    arsenal: list[str]
    overall_current_xwoba: float
    overall_optimized_xwoba: float
    expected_improvement_xwoba: float
    overall_current_rv: float
    overall_optimized_rv: float
    expected_improvement_rv: float
    segments: list[SegmentRecommendation] = field(default_factory=list)
    pairing_notes: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def optimize_pitcher(
    pitches: pd.DataFrame,
    model: OutcomeModel,
    *,
    pitcher: int | str | None = None,
    pitcher_name: str | None = None,
    min_arsenal_n: int = 30,
    min_segment_n: int = 40,
    min_pct: float = 0.03,
    max_pct: float = 0.55,
    max_shift: float = 0.15,
) -> PitcherRecommendation:
    """Optimize one pitcher's usage vs modeled pitch values."""
    prepared = prepare_pitches(pitches)
    subset = _select_pitcher(prepared, pitcher=pitcher, pitcher_name=pitcher_name)
    if subset.empty:
        raise ValueError(f"No pitches found for pitcher={pitcher!r} name={pitcher_name!r}")

    pitcher_id = int(subset["pitcher"].iloc[0])
    name = str(subset["player_name"].iloc[0])
    arsenal = arsenal_pitch_types(subset, min_n=min_arsenal_n)
    if len(arsenal) < 2:
        arsenal = arsenal_pitch_types(subset, min_n=10)
    if len(arsenal) < 2:
        raise ValueError(f"{name} has fewer than 2 pitch types with enough samples")

    subset = subset[subset["pitch_type"].isin(arsenal)].copy()
    pairing_notes = _pairing_notes(subset, arsenal)

    segments: list[SegmentRecommendation] = []
    # Primary split: platoon (batter side). Secondary: count state.
    for side, side_df in subset.groupby("batter_side"):
        if len(side_df) < min_segment_n:
            continue
        seg = _optimize_segment(
            side_df,
            model=model,
            arsenal=arsenal,
            segment=f"vs {side}",
            min_pct=min_pct,
            max_pct=max_pct,
            max_shift=max_shift,
        )
        segments.append(seg)

        for count_name, count_df in side_df.groupby("count_bucket"):
            if len(count_df) < min_segment_n:
                continue
            if count_name == "0-0":
                label = f"vs {side} | 0-0"
            else:
                label = f"vs {side} | {count_name}"
            segments.append(
                _optimize_segment(
                    count_df,
                    model=model,
                    arsenal=arsenal,
                    segment=label,
                    min_pct=min_pct,
                    max_pct=max_pct,
                    max_shift=max_shift,
                )
            )

    # Overall = pitch-weighted average of platoon segments only.
    platoon_segs = [s for s in segments if s.segment.startswith("vs ") and "|" not in s.segment]
    if not platoon_segs:
        platoon_segs = [
            _optimize_segment(
                subset,
                model=model,
                arsenal=arsenal,
                segment="overall",
                min_pct=min_pct,
                max_pct=max_pct,
                max_shift=max_shift,
            )
        ]
        segments = platoon_segs + segments

    total_n = sum(s.n_pitches for s in platoon_segs)
    w = np.array([s.n_pitches / total_n for s in platoon_segs], dtype=float)
    cur_x = float(np.dot(w, [s.current_xwoba for s in platoon_segs]))
    opt_x = float(np.dot(w, [s.optimized_xwoba for s in platoon_segs]))
    cur_rv = float(np.dot(w, [s.current_rv for s in platoon_segs]))
    opt_rv = float(np.dot(w, [s.optimized_rv for s in platoon_segs]))

    return PitcherRecommendation(
        pitcher_id=pitcher_id,
        pitcher_name=name,
        n_pitches=int(len(subset)),
        arsenal=arsenal,
        overall_current_xwoba=cur_x,
        overall_optimized_xwoba=opt_x,
        expected_improvement_xwoba=opt_x - cur_x,
        overall_current_rv=cur_rv,
        overall_optimized_rv=opt_rv,
        expected_improvement_rv=opt_rv - cur_rv,
        segments=segments,
        pairing_notes=pairing_notes,
        meta={"min_pct": min_pct, "max_pct": max_pct, "max_shift": max_shift},
    )


def optimize_pitchers(
    pitches: pd.DataFrame,
    model: OutcomeModel,
    *,
    pitcher_ids: list[int] | None = None,
    top_n: int = 3,
    **kwargs: Any,
) -> list[PitcherRecommendation]:
    prepared = prepare_pitches(pitches)
    if pitcher_ids is None:
        counts = prepared.groupby("pitcher").size().sort_values(ascending=False)
        pitcher_ids = [int(i) for i in counts.head(top_n).index.tolist()]
    return [
        optimize_pitcher(prepared, model, pitcher=pid, **kwargs) for pid in pitcher_ids
    ]


def _select_pitcher(
    df: pd.DataFrame,
    *,
    pitcher: int | str | None,
    pitcher_name: str | None,
) -> pd.DataFrame:
    if pitcher is not None:
        try:
            pid = int(pitcher)
            return df[df["pitcher"] == pid].copy()
        except (TypeError, ValueError):
            # Treat as name substring.
            pitcher_name = str(pitcher)

    if pitcher_name:
        needle = pitcher_name.strip().lower()
        names = df["player_name"].fillna("").astype(str)
        # Support "Last, First" and "First Last".
        mask = names.str.lower().str.contains(needle, regex=False)
        if not mask.any() and " " in needle:
            parts = [p for p in needle.replace(",", " ").split() if p]
            if len(parts) >= 2:
                # Try "last, first"
                alt = f"{parts[-1]}, {parts[0]}"
                mask = names.str.lower().str.contains(alt, regex=False)
                if not mask.any():
                    mask = names.str.lower().apply(
                        lambda s: all(p in s.lower() for p in parts)
                    )
        return df[mask].copy()
    raise ValueError("Provide --pitcher MLBAM id or name")


def _optimize_segment(
    seg: pd.DataFrame,
    *,
    model: OutcomeModel,
    arsenal: list[str],
    segment: str,
    min_pct: float,
    max_pct: float,
    max_shift: float,
) -> SegmentRecommendation:
    current = (
        seg["pitch_type"].value_counts(normalize=True).reindex(arsenal, fill_value=0.0)
    )
    current_pct = current.to_numpy(dtype=float)
    # Renormalize in case some arsenal pitches absent in segment.
    if current_pct.sum() <= 0:
        current_pct = np.ones(len(arsenal)) / len(arsenal)
    else:
        current_pct = current_pct / current_pct.sum()

    values = _expected_values(seg, model=model, arsenal=arsenal)
    rv = values["pred_rv"].to_numpy(dtype=float)
    xw = values["pred_xwoba"].to_numpy(dtype=float)

    opt_pct = _solve_usage(
        current_pct,
        values=xw,  # minimize expected xwOBA allowed against pitcher
        min_pct=min_pct,
        max_pct=max_pct,
        max_shift=max_shift,
    )

    cur_x = float(np.dot(current_pct, xw))
    opt_x = float(np.dot(opt_pct, xw))
    cur_rv = float(np.dot(current_pct, rv))
    opt_rv = float(np.dot(opt_pct, rv))

    changes = [
        UsageChange(
            pitch_type=pt,
            current_pct=float(current_pct[i]),
            recommended_pct=float(opt_pct[i]),
            delta_pct=float(opt_pct[i] - current_pct[i]),
        )
        for i, pt in enumerate(arsenal)
    ]
    changes.sort(key=lambda c: abs(c.delta_pct), reverse=True)

    return SegmentRecommendation(
        segment=segment,
        n_pitches=int(len(seg)),
        current_xwoba=cur_x,
        optimized_xwoba=opt_x,
        expected_improvement_xwoba=opt_x - cur_x,
        current_rv=cur_rv,
        optimized_rv=opt_rv,
        expected_improvement_rv=opt_rv - cur_rv,
        changes=changes,
    )


def _expected_values(
    seg: pd.DataFrame,
    *,
    model: OutcomeModel,
    arsenal: list[str],
) -> pd.DataFrame:
    """Average predicted RV/xwOBA for each arsenal pitch under segment contexts."""
    # Sample contexts to keep inference snappy on large segments.
    ctx = seg
    if len(ctx) > 400:
        ctx = ctx.sample(n=400, random_state=42)

    base = ctx[CONTEXT_FEATURE_COLS].copy()
    for col in CONTEXT_FEATURE_COLS:
        base[col] = pd.to_numeric(base[col], errors="coerce")
    base = base.fillna(base.median(numeric_only=True)).fillna(0.0)

    rows = []
    for pt in arsenal:
        feat = base.copy()
        for other in model.pitch_types:
            feat[f"{PITCH_ONEHOT_PREFIX}{other}"] = 0
        # Ensure arsenal pitch one-hot exists even if rare league-wide.
        col = f"{PITCH_ONEHOT_PREFIX}{pt}"
        if col not in feat.columns:
            feat[col] = 0
        feat[col] = 1
        # Adjust sequence flags relative to previous pitch.
        if "prev_pitch_type" in ctx.columns:
            feat["prev_same_pitch"] = (ctx["prev_pitch_type"].to_numpy() == pt).astype(int)
        pred_rv = model.predict_rv(feat)
        pred_x = model.predict_xwoba(feat)
        rows.append(
            {
                "pitch_type": pt,
                "pred_rv": float(np.mean(pred_rv)),
                "pred_xwoba": float(np.mean(pred_x)),
            }
        )
    return pd.DataFrame(rows)


def _solve_usage(
    current: np.ndarray,
    *,
    values: np.ndarray,
    min_pct: float,
    max_pct: float,
    max_shift: float,
) -> np.ndarray:
    n = len(current)
    # Established pitches (>=5%) can move within shift caps; fringe pitches stay fixed.
    lowers = []
    uppers = []
    for p in current:
        if p < 0.05:
            lowers.append(float(p))
            uppers.append(float(p))
        else:
            lo = max(min_pct, p - max_shift)
            hi = min(max_pct, p + max_shift)
            if lo > hi:
                lo, hi = hi, lo
            lowers.append(lo)
            uppers.append(hi)
    lowers_a = np.array(lowers, dtype=float)
    uppers_a = np.array(uppers, dtype=float)

    # If bounds cannot sum to 1, relax established pitches to [min_pct, max_pct].
    if lowers_a.sum() > 1.0 + 1e-6 or uppers_a.sum() < 1.0 - 1e-6:
        lowers_a = np.where(current >= 0.05, min_pct, current)
        uppers_a = np.where(current >= 0.05, max_pct, current)

    def objective(w: np.ndarray) -> float:
        return float(np.dot(w, values))

    cons = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    bounds = list(zip(lowers_a, uppers_a, strict=True))
    x0 = np.clip(current, lowers_a, uppers_a)
    if x0.sum() == 0:
        x0 = np.ones(n) / n
    else:
        x0 = x0 / x0.sum()

    result = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=cons,
        options={"maxiter": 200, "ftol": 1e-9},
    )
    if not result.success:
        # Greedy fallback: shift mass toward lowest-value pitches.
        w = current.copy()
        order = np.argsort(values)
        budget = max_shift
        for i in order:
            if w[i] < 0.05:
                continue
            target = min(uppers_a[i], w[i] + budget)
            gain = target - w[i]
            if gain <= 0:
                continue
            donors = np.argsort(-values)
            need = gain
            for j in donors:
                if j == i or w[j] < 0.05:
                    continue
                give = min(need, w[j] - lowers_a[j])
                if give <= 0:
                    continue
                w[j] -= give
                w[i] += give
                need -= give
                if need <= 1e-9:
                    break
            budget -= gain - need
            if budget <= 1e-9:
                break
        w = np.clip(w, 0, None)
        w = w / w.sum()
        return w

    w = np.clip(result.x, 0, None)
    return w / w.sum()


def _pairing_notes(df: pd.DataFrame, arsenal: list[str]) -> list[str]:
    notes: list[str] = []
    cols = ["release_speed", "pfx_x", "pfx_z", "release_pos_x", "release_pos_z"]
    for c in cols:
        if c not in df.columns:
            return notes
    means = df.groupby("pitch_type")[cols].mean()
    primary = df["pitch_type"].value_counts().idxmax()
    if primary not in means.index:
        return notes
    p = means.loc[primary]
    for pt in arsenal:
        if pt == primary or pt not in means.index:
            continue
        row = means.loc[pt]
        velo = abs(float(row["release_speed"] - p["release_speed"]))
        mov = float(
            np.sqrt((row["pfx_x"] - p["pfx_x"]) ** 2 + (row["pfx_z"] - p["pfx_z"]) ** 2)
        )
        rel = float(
            np.sqrt(
                (row["release_pos_x"] - p["release_pos_x"]) ** 2
                + (row["release_pos_z"] - p["release_pos_z"]) ** 2
            )
        )
        tunnel = "strong tunnel" if rel < 0.25 else ("moderate tunnel" if rel < 0.45 else "distinct release")
        notes.append(
            f"{pt} vs primary {primary}: velo sep {velo:.1f} mph, "
            f"move sep {mov:.1f} in, release {tunnel} ({rel:.2f} ft)"
        )
    return notes
