"""Pitch outcome model: predict run value / xwOBA given context + pitch choice."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from pitch_dataset.arsenal.features import (
    PITCH_ONEHOT_PREFIX,
    arsenal_pitch_types,
    build_model_matrix,
    prepare_pitches,
)

DEFAULT_MODEL_PATH = Path("models/outcome_model.joblib")


@dataclass
class OutcomeModel:
    """Trained dual-target pitch outcome model (RV + xwOBA)."""

    rv_model: HistGradientBoostingRegressor
    xwoba_model: HistGradientBoostingRegressor
    feature_names: list[str]
    pitch_types: list[str]
    meta: dict[str, Any] = field(default_factory=dict)

    def predict_rv(self, X: pd.DataFrame) -> np.ndarray:
        return self.rv_model.predict(_align_features(X, self.feature_names))

    def predict_xwoba(self, X: pd.DataFrame) -> np.ndarray:
        return self.xwoba_model.predict(_align_features(X, self.feature_names))

    def save(self, path: Path | str = DEFAULT_MODEL_PATH) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path


def load_outcome_model(path: Path | str = DEFAULT_MODEL_PATH) -> OutcomeModel:
    obj = joblib.load(path)
    if not isinstance(obj, OutcomeModel):
        raise TypeError(f"Expected OutcomeModel at {path}, got {type(obj)}")
    return obj


def train_outcome_model(
    pitches: pd.DataFrame,
    *,
    model_path: Path | str = DEFAULT_MODEL_PATH,
    test_size: float = 0.2,
    random_state: int = 42,
    min_pitch_n: int = 200,
) -> tuple[OutcomeModel, dict[str, Any]]:
    """Train outcome models and persist to disk."""
    prepared = prepare_pitches(pitches)
    pitch_types = arsenal_pitch_types(prepared, min_n=min_pitch_n)
    if len(pitch_types) < 2:
        pitch_types = arsenal_pitch_types(prepared, min_n=50)

    X, y_rv, y_xwoba = build_model_matrix(prepared, pitch_types=pitch_types)
    X_train, X_test, y_rv_train, y_rv_test, y_x_train, y_x_test = train_test_split(
        X,
        y_rv,
        y_xwoba,
        test_size=test_size,
        random_state=random_state,
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
    }

    model = OutcomeModel(
        rv_model=rv_model,
        xwoba_model=xwoba_model,
        feature_names=list(X.columns),
        pitch_types=pitch_types,
        meta=metrics,
    )
    model.save(model_path)
    return model, metrics


def score_pitch_choices(
    model: OutcomeModel,
    context_features: pd.DataFrame,
    pitch_types: list[str],
) -> pd.DataFrame:
    """Score each candidate pitch type for rows of shared context features.

    ``context_features`` should already include pitch one-hots for each candidate
    (one row per candidate pitch).
    """
    rv = model.predict_rv(context_features)
    xw = model.predict_xwoba(context_features)
    return pd.DataFrame(
        {
            "pitch_type": pitch_types,
            "pred_rv": rv,
            "pred_xwoba": xw,
        }
    )


def _align_features(X: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    aligned = X.copy()
    for name in feature_names:
        if name not in aligned.columns:
            aligned[name] = 0.0
    return aligned[feature_names].fillna(0.0)
