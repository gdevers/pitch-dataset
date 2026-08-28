"""Local dataset storage helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_DATA_DIR = Path("data")


def pitch_path(
    data_dir: Path | str,
    *,
    season: int,
    league: str,
) -> Path:
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"pitches_{league}_{season}.parquet"


def mlb_api_path(
    data_dir: Path | str,
    *,
    season: int,
    kind: str,
) -> Path:
    """Path for MLB Stats API parquet artifacts (games, rosters, etc.)."""
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"mlb_{kind}_{season}.parquet"


def fangraphs_path(
    data_dir: Path | str,
    *,
    season: int,
    stat_type: str,
) -> Path:
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"fangraphs_{stat_type}_{season}.parquet"


def chadwick_register_path(data_dir: Path | str) -> Path:
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / "chadwick_register.parquet"


def write_pitches(
    frame: pd.DataFrame,
    path: Path | str,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if frame.empty:
        # Still write an empty parquet with no rows for a stable path contract.
        frame.to_parquet(path, index=False)
    else:
        ordered = _sort_pitches(frame)
        ordered.to_parquet(path, index=False)
    return path


def write_parquet(frame: pd.DataFrame, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def read_pitches(path: Path | str) -> pd.DataFrame:
    return pd.read_parquet(path)


def read_parquet(path: Path | str) -> pd.DataFrame:
    return pd.read_parquet(path)


def _sort_pitches(frame: pd.DataFrame) -> pd.DataFrame:
    sort_cols = [
        c
        for c in ("game_date", "game_pk", "at_bat_number", "pitch_number")
        if c in frame.columns
    ]
    if not sort_cols:
        return frame
    return frame.sort_values(sort_cols, ascending=True).reset_index(drop=True)
