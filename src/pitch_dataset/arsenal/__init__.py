"""Pitch arsenal optimization: outcome model + counterfactual usage."""

from pitch_dataset.arsenal.optimize import optimize_pitcher, optimize_pitchers
from pitch_dataset.arsenal.outcome import OutcomeModel, load_outcome_model, train_outcome_model
from pitch_dataset.arsenal.report import format_recommendation_report

__all__ = [
    "OutcomeModel",
    "format_recommendation_report",
    "load_outcome_model",
    "optimize_pitcher",
    "optimize_pitchers",
    "train_outcome_model",
]
