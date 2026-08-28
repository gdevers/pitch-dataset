"""Helpers for joining Savant pitch data with FanGraphs and Chadwick IDs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pitch_dataset.storage import (
    chadwick_register_path,
    fangraphs_path,
    read_parquet,
    read_pitches,
)


def join_pitches_to_fangraphs(
    pitches: pd.DataFrame,
    *,
    register: pd.DataFrame,
    fangraphs_pitching: pd.DataFrame | None = None,
    fangraphs_batting: pd.DataFrame | None = None,
    role: str = "pitcher",
) -> pd.DataFrame:
    """Attach FanGraphs season stats to pitch rows via Chadwick MLBAM ids.

    Savant pitch columns ``pitcher`` and ``batter`` are MLBAM ids. Chadwick
    ``key_mlbam`` maps to ``key_fangraphs``, which joins to FanGraphs ``IDfg``.
    """
    if role not in {"pitcher", "batter"}:
        raise ValueError("role must be 'pitcher' or 'batter'")

    id_col = role
    fg_stats = fangraphs_pitching if role == "pitcher" else fangraphs_batting
    if fg_stats is None or fg_stats.empty:
        return pitches.copy()

    register_cols = register[
        ["key_mlbam", "key_fangraphs", "name_last", "name_first"]
    ].drop_duplicates(subset=["key_mlbam"])
    merged = pitches.merge(
        register_cols,
        left_on=id_col,
        right_on="key_mlbam",
        how="left",
        suffixes=("", f"_{role}"),
    )
    fg = fg_stats.copy()
    if "IDfg" not in fg.columns and "key_fangraphs" in fg.columns:
        fg = fg.rename(columns={"key_fangraphs": "IDfg"})
    stat_cols = [
        c
        for c in fg.columns
        if c not in {"IDfg", "season", "stat_type", "player_name", "Team", "Age", "Name"}
    ]
    fg_subset = fg[["IDfg"] + stat_cols].drop_duplicates(subset=["IDfg"])
    return merged.merge(
        fg_subset,
        left_on="key_fangraphs",
        right_on="IDfg",
        how="left",
        suffixes=("", f"_{role}_fg"),
    )


def load_join_bundle(
    data_dir: Path | str,
    *,
    season: int,
) -> dict[str, pd.DataFrame]:
    """Load pitches, Chadwick register, and FanGraphs frames from ``data_dir``."""
    root = Path(data_dir)
    bundle = {
        "pitches": read_pitches(root / f"pitches_mlb_{season}.parquet"),
        "register": read_parquet(chadwick_register_path(root)),
        "fangraphs_batting": read_parquet(
            fangraphs_path(root, season=season, stat_type="batting")
        ),
        "fangraphs_pitching": read_parquet(
            fangraphs_path(root, season=season, stat_type="pitching")
        ),
    }
    return bundle
