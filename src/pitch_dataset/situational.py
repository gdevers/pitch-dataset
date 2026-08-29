"""Situational pitch selection: context + pitch type → expected xwOBA / run value.

Answers: *Against this batter, in this count, right now — which pitch minimizes damage?*
Unlike arsenal optimization (season usage mix), this scores discrete pitch choices for a
single micro-decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from pitch_dataset.arsenal import (
    CONTEXT_FEATURE_COLS,
    EXCLUDED_PITCH_TYPES,
    PAIRING_FEATURE_COLS,
    PITCH_ONEHOT_PREFIX,
    PITCH_SHAPE_FEATURE_COLS,
    OutcomeModel,
    arsenal_pitch_types,
    context_row_features,
    pairing_features_for_type,
    pitcher_arsenal_means,
    prepare_pitches,
    primary_pitch_type,
)
from pitch_dataset.joins import join_pitches_to_fangraphs
from pitch_dataset.storage import chadwick_register_path, fangraphs_path, read_parquet

# Zone/location is unknown at pitch-selection time — exclude from situational features.
LOCATION_FEATURE_COLS = frozenset(
    {"zone_heart", "zone_shadow", "zone_chase", "zone_waste", "plate_x", "plate_z"}
)

SITUATIONAL_EXTRA_COLS = [
    "leverage_proxy",
    "leverage_high",
    "leverage_medium",
    "fg_batter_woba_platoon",
    "fg_batter_xwoba_platoon",
]

SITUATIONAL_CONTEXT_COLS = [
    c for c in CONTEXT_FEATURE_COLS if c not in LOCATION_FEATURE_COLS
] + SITUATIONAL_EXTRA_COLS

DEFAULT_SITUATIONAL_MODEL_PATH = Path("models/situational_model.joblib")

DEMO_MATCHUPS: list[dict[str, Any]] = [
    {
        "pitcher": "Cease",
        "batter": "Devers",
        "count": "1-2",
        "leverage": "high",
        "stand": "L",
        "p_throws": "R",
        "outs": 2,
        "runners_on": 1,
        "score_diff": 0,
        "prev_pitch": "FF",
        "label": "Cease vs Devers",
    },
    {
        "pitcher": "Cease",
        "batter": "Abreu",
        "count": "0-2",
        "leverage": "medium",
        "stand": "L",
        "p_throws": "R",
        "outs": 1,
        "label": "Cease vs Wilyer Abreu",
    },
    {
        "pitcher": "Skubal",
        "batter": "Judge",
        "count": "2-2",
        "leverage": "high",
        "stand": "R",
        "p_throws": "L",
        "outs": 2,
        "runners_on": 2,
        "score_diff": -1,
        "label": "Skubal vs Aaron Judge",
    },
    {
        "pitcher": "Skenes",
        "batter": "Ohtani",
        "count": "1-1",
        "leverage": "medium",
        "stand": "L",
        "p_throws": "R",
        "outs": 0,
        "label": "Skenes vs Ohtani",
    },
    {
        "pitcher": "Gausman",
        "batter": "Guerrero",
        "count": "3-2",
        "leverage": "high",
        "stand": "R",
        "p_throws": "R",
        "outs": 2,
        "runners_on": 1,
        "score_diff": 1,
        "label": "Gausman vs Vladimir Guerrero Jr.",
    },
]


@dataclass
class PitchScore:
    pitch_type: str
    pred_xwoba: float
    pred_rv: float
    is_recommended: bool = False
    is_default: bool = False


@dataclass
class SituationalRecommendation:
    pitcher_id: int
    pitcher_name: str
    batter_id: int
    batter_name: str
    count: str
    balls: int
    strikes: int
    stand: str
    p_throws: str
    batter_side: str
    leverage: str
    leverage_proxy: float
    outs: int
    runners_on: int
    score_diff: int
    prev_pitch: str | None
    arsenal: list[str]
    default_pitch: str
    recommended_pitch: str
    scores: list[PitchScore]
    expected_improvement_xwoba: float
    expected_improvement_rv: float
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SituationalModel:
    """Dual-target situational pitch-outcome model (RV + xwOBA)."""

    rv_model: HistGradientBoostingRegressor
    xwoba_model: HistGradientBoostingRegressor
    feature_names: list[str]
    pitch_types: list[str]
    meta: dict[str, Any] = field(default_factory=dict)

    def predict_rv(self, X: pd.DataFrame) -> np.ndarray:
        return self.rv_model.predict(_align_features(X, self.feature_names))

    def predict_xwoba(self, X: pd.DataFrame) -> np.ndarray:
        return self.xwoba_model.predict(_align_features(X, self.feature_names))

    def save(self, path: Path | str = DEFAULT_SITUATIONAL_MODEL_PATH) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path


def load_situational_model(path: Path | str = DEFAULT_SITUATIONAL_MODEL_PATH) -> SituationalModel:
    obj = joblib.load(path)
    if not isinstance(obj, SituationalModel):
        raise TypeError(f"Expected SituationalModel at {path}, got {type(obj)}")
    return obj


def parse_count(count: str) -> tuple[int, int]:
    parts = count.strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid count {count!r}; expected e.g. '1-2'")
    return int(parts[0]), int(parts[1])


def leverage_label(proxy: float) -> str:
    if proxy >= 0.55:
        return "high"
    if proxy >= 0.30:
        return "medium"
    return "low"


def compute_leverage_proxy(
    *,
    inning: int = 5,
    outs: int = 0,
    runners_on: int = 0,
    score_diff: int = 0,
) -> float:
    """Simple leverage index in [0, 1] from game state (no play-by-play LI table)."""
    late = min(1.0, max(0.0, (inning - 6) / 3.0))
    close = 1.0 if abs(score_diff) <= 2 else max(0.0, 1.0 - (abs(score_diff) - 2) / 5.0)
    risp = 1.0 if runners_on >= 1 else 0.0
    two_out = 1.0 if outs == 2 else 0.0
    return float(0.30 * late + 0.30 * close + 0.20 * risp + 0.20 * two_out)


def _leverage_dummies(proxy: float) -> tuple[float, float, float]:
    label = leverage_label(proxy)
    return (
        float(label == "high"),
        float(label == "medium"),
        float(label == "low"),
    )


def prepare_situational_pitches(
    pitches: pd.DataFrame,
    *,
    data_dir: Path | str = "data",
    season: int | None = None,
) -> pd.DataFrame:
    """Annotate pitches with situational features (no zone/location)."""
    out = prepare_pitches(pitches)
    out["leverage_proxy"] = [
        compute_leverage_proxy(
            inning=int(row.get("inning", 5) or 5),
            outs=int(row.get("outs_when_up", 0) or 0),
            runners_on=int(row.get("runners_on", 0) or 0),
            score_diff=int(row.get("score_diff", 0) or 0),
        )
        for _, row in out.iterrows()
    ]
    hi, med, lo = zip(
        *[_leverage_dummies(p) for p in out["leverage_proxy"]], strict=False
    )
    out["leverage_high"] = hi
    out["leverage_medium"] = med
    out["leverage_low"] = lo

    out["fg_batter_woba_platoon"] = 0.320
    out["fg_batter_xwoba_platoon"] = 0.320
    if season is not None:
        root = Path(data_dir)
        reg_path = chadwick_register_path(root)
        splits_path = fangraphs_path(root, season=season, stat_type="batting_splits")
        if reg_path.exists() and splits_path.exists():
            register = read_parquet(reg_path)
            splits = read_parquet(splits_path)
            joined = join_pitches_to_fangraphs(
                out,
                register=register,
                fangraphs_batting=splits,
                role="batter",
            )
            woba_l = pd.to_numeric(joined.get("wOBA_vs_l"), errors="coerce")
            woba_r = pd.to_numeric(joined.get("wOBA_vs_r"), errors="coerce")
            xwoba_l = pd.to_numeric(joined.get("xwOBA_vs_l"), errors="coerce")
            xwoba_r = pd.to_numeric(joined.get("xwOBA_vs_r"), errors="coerce")
            throws = joined["p_throws"].fillna("R")
            out["fg_batter_woba_platoon"] = np.where(
                throws == "L",
                woba_r.fillna(woba_l).fillna(0.320),
                woba_l.fillna(woba_r).fillna(0.320),
            )
            out["fg_batter_xwoba_platoon"] = np.where(
                throws == "L",
                xwoba_r.fillna(xwoba_l).fillna(0.320),
                xwoba_l.fillna(xwoba_r).fillna(0.320),
            )
    out.attrs["situational_prepared"] = True
    return out


def build_situational_matrix(
    df: pd.DataFrame,
    *,
    pitch_types: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    frame = df.dropna(subset=["target_rv"]).copy()
    pts = list(pitch_types) if pitch_types is not None else sorted(frame["pitch_type"].unique())
    X = frame[SITUATIONAL_CONTEXT_COLS].copy()
    for col in SITUATIONAL_CONTEXT_COLS:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    X = X.fillna(X.median(numeric_only=True))
    for pt in pts:
        X[f"{PITCH_ONEHOT_PREFIX}{pt}"] = (frame["pitch_type"] == pt).astype(int)
    y_rv = frame["target_rv"].astype(float)
    y_xwoba = frame["target_xwoba"].astype(float)
    return X, y_rv, y_xwoba


def train_situational_model(
    pitches: pd.DataFrame,
    *,
    model_path: Path | str = DEFAULT_SITUATIONAL_MODEL_PATH,
    data_dir: Path | str = "data",
    season: int | None = None,
    test_size: float = 0.2,
    random_state: int = 42,
    min_pitch_n: int = 200,
) -> tuple[SituationalModel, dict[str, Any]]:
    prepared = prepare_situational_pitches(
        pitches, data_dir=data_dir, season=season
    )
    pitch_types = arsenal_pitch_types(prepared, min_n=min_pitch_n)
    if len(pitch_types) < 2:
        pitch_types = arsenal_pitch_types(prepared, min_n=50)

    X, y_rv, y_xwoba = build_situational_matrix(prepared, pitch_types=pitch_types)
    X_train, X_test, y_rv_train, y_rv_test, y_x_train, y_x_test = train_test_split(
        X, y_rv, y_xwoba, test_size=test_size, random_state=random_state
    )

    rv_model = HistGradientBoostingRegressor(
        max_depth=6,
        learning_rate=0.08,
        max_iter=250,
        l2_regularization=0.1,
        random_state=random_state,
    )
    xwoba_model = HistGradientBoostingRegressor(
        max_depth=6,
        learning_rate=0.08,
        max_iter=250,
        l2_regularization=0.1,
        random_state=random_state,
    )
    rv_model.fit(X_train, y_rv_train)
    xwoba_model.fit(X_train, y_x_train)

    rv_pred = rv_model.predict(X_test)
    x_pred = xwoba_model.predict(X_test)
    metrics = {
        "n_pitches": int(len(prepared)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "date_min": str(prepared["game_date"].min().date())
        if "game_date" in prepared.columns
        else None,
        "date_max": str(prepared["game_date"].max().date())
        if "game_date" in prepared.columns
        else None,
        "rv_mae": float(mean_absolute_error(y_rv_test, rv_pred)),
        "rv_r2": float(r2_score(y_rv_test, rv_pred)),
        "xwoba_mae": float(mean_absolute_error(y_x_test, x_pred)),
        "xwoba_r2": float(r2_score(y_x_test, x_pred)),
        "pitch_types": pitch_types,
        "feature_cols": SITUATIONAL_CONTEXT_COLS,
    }

    model = SituationalModel(
        rv_model=rv_model,
        xwoba_model=xwoba_model,
        feature_names=list(X.columns),
        pitch_types=pitch_types,
        meta=metrics,
    )
    model.save(model_path)
    return model, metrics


def _select_player(
    df: pd.DataFrame,
    *,
    player: int | str | None,
    player_name: str | None,
    id_col: str,
    name_col: str = "player_name",
) -> pd.Series | None:
    if player is not None:
        try:
            pid = int(player)
            rows = df[df[id_col] == pid]
            if not rows.empty:
                return rows.iloc[0]
        except (TypeError, ValueError):
            player_name = str(player)

    if player_name:
        needle = player_name.strip().lower()
        if id_col in {"batter", "pitcher"}:
            from pitch_dataset.storage import read_parquet, chadwick_register_path

            reg = read_parquet(chadwick_register_path("data"))
            mask = reg["name_last"].str.lower().str.contains(needle, regex=False)
            if " " in needle or "," in needle:
                parts = [p for p in needle.replace(",", " ").split() if p]
                if len(parts) >= 2:
                    mask = mask & reg["name_last"].str.lower().str.contains(
                        parts[-1], regex=False
                    )
                    if parts[0] not in parts[-1]:
                        mask = mask & reg["name_first"].str.lower().str.contains(
                            parts[0], regex=False
                        )
            hits = reg[mask]
            if not hits.empty:
                ids_in_data = set(df[id_col].dropna().astype(int).unique())
                hits = hits[hits["key_mlbam"].isin(ids_in_data)]
                if not hits.empty:
                    counts = df[id_col].value_counts()
                    hits = hits.assign(
                        _n=hits["key_mlbam"].map(lambda i: counts.get(i, 0))
                    ).sort_values("_n", ascending=False)
                    bid = int(hits.iloc[0]["key_mlbam"])
                    return df[df[id_col] == bid].iloc[0]
        names = df.get(name_col, pd.Series("", index=df.index)).fillna("").astype(str)
        mask = names.str.lower().str.contains(needle, regex=False)
        if mask.any():
            return df[mask].iloc[0]
    return None


def _default_pitch_in_situation(
    pitcher_df: pd.DataFrame,
    *,
    balls: int,
    strikes: int,
    stand: str,
) -> str:
    sub = pitcher_df[
        (pitcher_df["balls"] == balls)
        & (pitcher_df["strikes"] == strikes)
        & (pitcher_df["stand"] == stand)
    ]
    if sub.empty:
        sub = pitcher_df[
            (pitcher_df["balls"] == balls) & (pitcher_df["strikes"] == strikes)
        ]
    if sub.empty:
        sub = pitcher_df
    counts = sub["pitch_type"].value_counts()
    return str(counts.idxmax()) if not counts.empty else "FF"


def _build_context_row(
    *,
    balls: int,
    strikes: int,
    stand: str,
    p_throws: str,
    outs: int,
    runners_on: int,
    score_diff: int,
    leverage: str | None,
    tto: int,
    batter_xwoba_prior: float,
    prev_pitch: str | None,
    fg_batter_woba_platoon: float,
    fg_batter_xwoba_platoon: float,
    pitcher_df: pd.DataFrame,
) -> pd.Series:
    platoon_rh = int(
        (p_throws == "R" and stand == "R") or (p_throws == "L" and stand == "L")
    )
    count_bucket = _count_bucket(balls, strikes)
    proxy = compute_leverage_proxy(
        inning=8 if leverage == "high" else 5,
        outs=outs,
        runners_on=runners_on,
        score_diff=score_diff,
    )
    if leverage in {"high", "medium", "low"}:
        proxy = {"high": 0.65, "medium": 0.40, "low": 0.15}[leverage]
    hi, med, lo = _leverage_dummies(proxy)

    row = {
        "platoon_rh": platoon_rh,
        "balls": balls,
        "strikes": strikes,
        "count_ahead_hit": int(count_bucket == "ahead_hit"),
        "count_ahead_pit": int(count_bucket == "ahead_pit"),
        "count_even": int(count_bucket in {"even", "0-0"}),
        "count_full": int(count_bucket == "full"),
        "is_2k": int(strikes == 2),
        "tto": tto,
        "outs_when_up": outs,
        "runners_on": runners_on,
        "score_diff": score_diff,
        "batter_xwoba_prior": batter_xwoba_prior,
        "prev_same_pitch": 0,
        "prev_is_fastball": int(prev_pitch in {"FF", "SI", "FC", "FA"} if prev_pitch else 0),
        "leverage_proxy": proxy,
        "leverage_high": hi,
        "leverage_medium": med,
        "leverage_low": lo,
        "fg_batter_woba_platoon": fg_batter_woba_platoon,
        "fg_batter_xwoba_platoon": fg_batter_xwoba_platoon,
    }
    for col in PITCH_SHAPE_FEATURE_COLS + PAIRING_FEATURE_COLS:
        row[col] = 0.0

    medians = pitcher_df.reindex(columns=SITUATIONAL_CONTEXT_COLS).median(numeric_only=True)
    for col in SITUATIONAL_CONTEXT_COLS:
        if col not in row:
            row[col] = float(medians.get(col, 0.0))

    series = pd.Series(row)
    series["prev_pitch_type"] = prev_pitch or "NONE"
    return series


def _count_bucket(balls: int, strikes: int) -> str:
    from pitch_dataset.arsenal import COUNT_BUCKETS

    return COUNT_BUCKETS.get((balls, strikes), "even")


def recommend_pitch(
    pitches: pd.DataFrame,
    model: SituationalModel,
    *,
    pitcher: int | str,
    batter: int | str,
    count: str,
    leverage: str | None = None,
    outs: int | None = None,
    stand: str | None = None,
    p_throws: str | None = None,
    runners_on: int | None = None,
    score_diff: int | None = None,
    prev_pitch: str | None = None,
    tto: int = 1,
    data_dir: Path | str = "data",
    season: int | None = None,
) -> SituationalRecommendation:
    """Score each arsenal pitch for a single situational decision."""
    prepared = prepare_situational_pitches(
        pitches, data_dir=data_dir, season=season
    )
    balls, strikes = parse_count(count)

    pitcher_row = _select_player(
        prepared, player=pitcher, player_name=None, id_col="pitcher"
    )
    if pitcher_row is None:
        pitcher_row = _select_player(
            prepared, player=None, player_name=str(pitcher), id_col="pitcher"
        )
    if pitcher_row is None:
        raise ValueError(f"Pitcher not found: {pitcher!r}")

    batter_row = _select_player(
        prepared, player=batter, player_name=None, id_col="batter", name_col="player_name"
    )
    if batter_row is None:
        batter_row = _select_player(
            prepared, player=None, player_name=str(batter), id_col="batter"
        )
    if batter_row is None:
        raise ValueError(f"Batter not found: {batter!r}")

    pitcher_id = int(pitcher_row["pitcher"])
    batter_id = int(batter_row["batter"])
    pitcher_name = str(
        prepared.loc[prepared["pitcher"] == pitcher_id, "player_name"].iloc[0]
    )
    batter_name = _batter_display_name(batter_id, data_dir)

    p_throws = (p_throws or pitcher_row.get("p_throws", "R") or "R").upper()
    stand = (stand or batter_row.get("stand", "R") or "R").upper()

    pitcher_df = prepared[prepared["pitcher"] == pitcher_id].copy()
    arsenal = [pt for pt in arsenal_pitch_types(pitcher_df, min_n=25) if pt in model.pitch_types]
    if len(arsenal) < 2:
        arsenal = [
            pt
            for pt in arsenal_pitch_types(pitcher_df, min_n=10)
            if pt in model.pitch_types
        ]
    if len(arsenal) < 2:
        raise ValueError(f"{pitcher_name} has fewer than 2 modeled pitch types")

    matchup = pitcher_df[pitcher_df["batter"] == batter_id]
    batter_prior = float(
        matchup["target_xwoba"].mean()
        if len(matchup) >= 5
        else prepared.loc[prepared["batter"] == batter_id, "batter_xwoba_prior"].median()
    )
    fg_woba = float(
        prepared.loc[prepared["batter"] == batter_id, "fg_batter_woba_platoon"].median()
    )
    fg_xwoba = float(
        prepared.loc[prepared["batter"] == batter_id, "fg_batter_xwoba_platoon"].median()
    )

    if outs is None:
        outs = int(pitcher_row.get("outs_when_up", 0) or 0)
    if runners_on is None:
        runners_on = int(pitcher_row.get("runners_on", 0) or 0)
    if score_diff is None:
        score_diff = int(pitcher_row.get("score_diff", 0) or 0)

    ctx_row = _build_context_row(
        balls=balls,
        strikes=strikes,
        stand=stand,
        p_throws=p_throws,
        outs=outs,
        runners_on=runners_on,
        score_diff=score_diff,
        leverage=leverage,
        tto=tto,
        batter_xwoba_prior=batter_prior,
        prev_pitch=prev_pitch,
        fg_batter_woba_platoon=fg_woba,
        fg_batter_xwoba_platoon=fg_xwoba,
        pitcher_df=pitcher_df,
    )

    arsenal_means = pitcher_arsenal_means(pitcher_df)
    primary = primary_pitch_type(pitcher_df)
    feat_df = context_row_features(
        ctx_row,
        arsenal,
        arsenal_means=arsenal_means,
        primary_pitch=primary,
    )
    for col in SITUATIONAL_EXTRA_COLS:
        feat_df[col] = float(ctx_row[col])
    for pt_col in model.feature_names:
        if pt_col.startswith(PITCH_ONEHOT_PREFIX) and pt_col not in feat_df.columns:
            feat_df[pt_col] = 0

    pred_rv = model.predict_rv(feat_df)
    pred_xw = model.predict_xwoba(feat_df)

    default_pt = _default_pitch_in_situation(
        pitcher_df, balls=balls, strikes=strikes, stand=stand
    )
    if default_pt not in arsenal:
        default_pt = arsenal[0]

    scores = [
        PitchScore(
            pitch_type=pt,
            pred_xwoba=float(pred_xw[i]),
            pred_rv=float(pred_rv[i]),
            is_default=(pt == default_pt),
        )
        for i, pt in enumerate(arsenal)
    ]
    scores.sort(key=lambda s: s.pred_xwoba)
    best = scores[0]
    best.is_recommended = True
    default_score = next(s for s in scores if s.is_default)
    improvement_xw = default_score.pred_xwoba - best.pred_xwoba
    improvement_rv = best.pred_rv - default_score.pred_rv

    proxy = float(ctx_row["leverage_proxy"])
    lev = leverage or leverage_label(proxy)

    return SituationalRecommendation(
        pitcher_id=pitcher_id,
        pitcher_name=pitcher_name,
        batter_id=batter_id,
        batter_name=batter_name,
        count=count,
        balls=balls,
        strikes=strikes,
        stand=stand,
        p_throws=p_throws,
        batter_side="LHH" if stand == "L" else "RHH",
        leverage=lev,
        leverage_proxy=proxy,
        outs=outs,
        runners_on=runners_on,
        score_diff=score_diff,
        prev_pitch=prev_pitch,
        arsenal=arsenal,
        default_pitch=default_pt,
        recommended_pitch=best.pitch_type,
        scores=scores,
        expected_improvement_xwoba=improvement_xw,
        expected_improvement_rv=improvement_rv,
        meta={"n_pitcher_pitches": len(pitcher_df), "n_matchup_pitches": len(matchup)},
    )


def _batter_display_name(batter_id: int, data_dir: Path | str) -> str:
    reg = read_parquet(chadwick_register_path(Path(data_dir)))
    row = reg[reg["key_mlbam"] == batter_id]
    if not row.empty:
        return f"{row.iloc[0]['name_first']} {row.iloc[0]['name_last']}"
    return str(batter_id)


def _align_features(X: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    aligned = X.copy()
    for name in feature_names:
        if name not in aligned.columns:
            aligned[name] = 0.0
    return aligned[feature_names].fillna(0.0)


def format_situational_text(rec: SituationalRecommendation) -> str:
    """Plain-text output matching the product example."""
    lines = [
        f"{_short_name(rec.pitcher_name)} vs {_short_name(rec.batter_name)} "
        f"| {rec.batter_side} | {rec.count} | {rec.leverage} leverage",
        f"Recommended: {rec.recommended_pitch} (not {rec.default_pitch})"
        if rec.recommended_pitch != rec.default_pitch
        else f"Recommended: {rec.recommended_pitch} (matches default)",
    ]
    for s in rec.scores:
        marker = "  ← pick" if s.is_recommended else ""
        lines.append(f"  {s.pitch_type}: pred xwOBA {s.pred_xwoba:.3f}{marker}")
    lines.append(
        f"Expected improvement vs default: "
        f"{-rec.expected_improvement_xwoba:+.3f} xwOBA"
    )
    return "\n".join(lines)


def _short_name(full: str) -> str:
    if "," in full:
        parts = [p.strip() for p in full.split(",", 1)]
        return parts[0]
    parts = full.split()
    return parts[-1] if parts else full


def format_situational_report(
    recs: list[SituationalRecommendation] | SituationalRecommendation,
    *,
    title: str = "Situational Pitch Selection Report",
    data_note: str | None = None,
) -> str:
    if isinstance(recs, SituationalRecommendation):
        recs = [recs]
    lines = [f"# {title}", ""]
    if data_note:
        lines.extend([data_note, ""])
    lines.append(
        "Micro pitch-choice recommendations: which pitch **minimizes predicted xwOBA** "
        "for this batter, count, and game state — not season-long usage optimization."
    )
    lines.append("")
    for rec in recs:
        lines.extend(_format_rec_md(rec))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_rec_md(rec: SituationalRecommendation) -> list[str]:
    lines = [
        f"## {_short_name(rec.pitcher_name)} vs {_short_name(rec.batter_name)}",
        "",
        f"- Count: **{rec.count}** | {rec.batter_side} vs {rec.p_throws}HP | "
        f"{rec.leverage} leverage (proxy {rec.leverage_proxy:.2f})",
        f"- Outs: {rec.outs} | Runners on: {rec.runners_on} | Score diff (fld-bat): {rec.score_diff}",
    ]
    if rec.prev_pitch:
        lines.append(f"- Previous pitch: **{rec.prev_pitch}**")
    lines.append(
        f"- Recommended: **{rec.recommended_pitch}** "
        f"(default in situation: {rec.default_pitch})"
    )
    lines.append(
        f"- Expected improvement vs default: **{-rec.expected_improvement_xwoba:+.3f} xwOBA**"
    )
    lines.append("")
    lines.append("| Pitch | Pred xwOBA | Pred RV | |")
    lines.append("| --- | ---: | ---: | --- |")
    for s in rec.scores:
        flag = "pick" if s.is_recommended else ("default" if s.is_default else "")
        lines.append(
            f"| {s.pitch_type} | {s.pred_xwoba:.3f} | {s.pred_rv:+.4f} | {flag} |"
        )
    return lines


def write_situational_report(
    recs: list[SituationalRecommendation] | SituationalRecommendation,
    path: Path | str,
    **kwargs,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_situational_report(recs, **kwargs), encoding="utf-8")
    return path


def recommendation_to_dict(rec: SituationalRecommendation) -> dict[str, Any]:
    return {
        "pitcher_id": rec.pitcher_id,
        "pitcher_name": rec.pitcher_name,
        "batter_id": rec.batter_id,
        "batter_name": rec.batter_name,
        "count": rec.count,
        "batter_side": rec.batter_side,
        "p_throws": rec.p_throws,
        "leverage": rec.leverage,
        "leverage_proxy": rec.leverage_proxy,
        "outs": rec.outs,
        "runners_on": rec.runners_on,
        "score_diff": rec.score_diff,
        "prev_pitch": rec.prev_pitch,
        "default_pitch": rec.default_pitch,
        "recommended_pitch": rec.recommended_pitch,
        "expected_improvement_xwoba": rec.expected_improvement_xwoba,
        "scores": [
            {
                "pitch_type": s.pitch_type,
                "pred_xwoba": s.pred_xwoba,
                "pred_rv": s.pred_rv,
                "is_recommended": s.is_recommended,
                "is_default": s.is_default,
            }
            for s in rec.scores
        ],
    }


def write_situational_html(
    recs: list[SituationalRecommendation],
    path: Path | str,
    *,
    data_note: str | None = None,
) -> Path:
    """Self-contained interactive HTML game card."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [recommendation_to_dict(r) for r in recs]
    matchups = DEMO_MATCHUPS
    html = _HTML_TEMPLATE.replace("__DATA__", json.dumps(payload))
    html = html.replace("__MATCHUPS__", json.dumps(matchups))
    html = html.replace("__DATA_NOTE__", data_note or "")
    path.write_text(html, encoding="utf-8")
    return path


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Situational Pitch Selection</title>
  <style>
    :root {
      --bg: #f7f7f5; --fg: #1a1a1a; --muted: #5c5c5c; --line: #d8d8d4;
      --accent: #1f4b99; --good: #1f6b3a; --card: #fff; --pick: #1f6b3a;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font: 15px/1.45 "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--fg); background: var(--bg); }
    main { max-width: 960px; margin: 0 auto; padding: 32px 20px 56px; }
    h1 { font: 600 26px/1.2 sans-serif; margin: 0 0 6px; letter-spacing: -0.02em; }
    h2 { font: 600 17px/1.3 sans-serif; margin: 28px 0 10px; }
    p, .meta { color: var(--muted); margin: 0 0 10px; }
    .controls { display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0; }
    select, button {
      font: inherit; padding: 8px 12px; border: 1px solid var(--line);
      border-radius: 4px; background: var(--card);
    }
    button { background: var(--accent); color: #fff; border-color: var(--accent); cursor: pointer; }
    .hero { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 16px 0; }
    .stat { background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; }
    .stat .v { font: 600 19px/1.2 sans-serif; }
    .stat .l { font-size: 11px; color: var(--muted); margin-top: 3px; }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 16px 18px; }
    .bar-row { display: grid; grid-template-columns: 44px 1fr 72px; gap: 8px; align-items: center; margin: 6px 0; }
    .bar-track { height: 22px; background: #eee; border-radius: 3px; position: relative; overflow: hidden; }
    .bar-fill { height: 100%; background: var(--accent); border-radius: 3px; opacity: 0.85; }
    .bar-fill.pick { background: var(--pick); }
    .bar-fill.def { background: #8a8a84; }
    .tag { font-size: 11px; color: var(--muted); }
    .pick-label { color: var(--pick); font-weight: 600; }
  </style>
</head>
<body>
<main>
  <h1>Situational Pitch Selection</h1>
  <p class="meta">__DATA_NOTE__</p>
  <p>Against this batter, in this count, right now — which pitch minimizes damage?</p>
  <div class="controls">
    <select id="matchup"></select>
    <button type="button" id="show">Show</button>
  </div>
  <div id="panel"></div>
</main>
<script>
const RECS = __DATA__;
const MATCHUPS = __MATCHUPS__;

const sel = document.getElementById('matchup');
MATCHUPS.forEach((m, i) => {
  const o = document.createElement('option');
  o.value = i;
  o.textContent = m.label || `${m.pitcher} vs ${m.batter} | ${m.count}`;
  sel.appendChild(o);
});

function shortName(n) {
  if (!n) return '';
  if (n.includes(',')) return n.split(',')[0].trim();
  const p = n.trim().split(/\s+/);
  return p[p.length - 1];
}

function render(i) {
  const rec = RECS[i];
  if (!rec) return;
  const maxX = Math.max(...rec.scores.map(s => s.pred_xwoba));
  const minX = Math.min(...rec.scores.map(s => s.pred_xwoba));
  const span = Math.max(0.001, maxX - minX);
  const imp = (-rec.expected_improvement_xwoba).toFixed(3);
  const impSign = rec.expected_improvement_xwoba >= 0 ? '' : '+';
  let bars = rec.scores.map(s => {
    const w = ((s.pred_xwoba - minX) / span) * 100;
    const cls = s.is_recommended ? 'pick' : (s.is_default ? 'def' : '');
    const tag = s.is_recommended ? '<span class="pick-label">pick</span>' :
      (s.is_default ? '<span class="tag">default</span>' : '');
    return `<div class="bar-row">
      <div><strong>${s.pitch_type}</strong></div>
      <div class="bar-track"><div class="bar-fill ${cls}" style="width:${Math.max(8,w)}%"></div></div>
      <div>${s.pred_xwoba.toFixed(3)} ${tag}</div>
    </div>`;
  }).join('');
  document.getElementById('panel').innerHTML = `
    <div class="hero">
      <div class="stat"><div class="v">${shortName(rec.pitcher_name)}</div><div class="l">Pitcher</div></div>
      <div class="stat"><div class="v">${shortName(rec.batter_name)}</div><div class="l">Batter · ${rec.batter_side}</div></div>
      <div class="stat"><div class="v">${rec.count}</div><div class="l">${rec.leverage} leverage</div></div>
      <div class="stat"><div class="v">${rec.recommended_pitch}</div><div class="l">vs default ${rec.default_pitch}</div></div>
    </div>
    <div class="card">
      <h2>Recommended: ${rec.recommended_pitch}${rec.recommended_pitch !== rec.default_pitch ? ` (not ${rec.default_pitch})` : ''}</h2>
      <p>Expected improvement vs default: <strong>${impSign}${imp} xwOBA</strong></p>
      ${bars}
    </div>`;
}

document.getElementById('show').onclick = () => render(+sel.value);
render(0);
</script>
</body>
</html>
"""
