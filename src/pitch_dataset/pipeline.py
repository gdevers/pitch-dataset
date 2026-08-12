"""High-level pull orchestration for MLB and MiLB pitch datasets."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Literal, Sequence

import pandas as pd
from tqdm import tqdm

from pitch_dataset.savant import (
    DEFAULT_MINOR_LEVELS,
    SavantError,
    fetch_mlb_pitches,
    fetch_minors_pitches,
    make_client,
)
from pitch_dataset.seasons import DEFAULT_SEASON, iter_date_chunks, season_date_range
from pitch_dataset.storage import pitch_path, write_pitches

logger = logging.getLogger(__name__)

LeagueChoice = Literal["mlb", "minors", "all"]


@dataclass(frozen=True)
class PullResult:
    season: int
    league: str
    start: date
    end: date
    rows: int
    path: Path | None
    frame: pd.DataFrame


def pull_pitches(
    *,
    season: int = DEFAULT_SEASON,
    league: LeagueChoice = "all",
    start: date | str | None = None,
    end: date | str | None = None,
    levels: Sequence[str] = DEFAULT_MINOR_LEVELS,
    data_dir: Path | str = "data",
    chunk_days: int = 1,
    write: bool = True,
    progress: bool = True,
) -> list[PullResult]:
    """Pull pitch-level Statcast data for MLB and/or MiLB.

    Defaults to the **2026** season window (clamped to today). Results are
    written as Parquet under ``data_dir`` unless ``write=False``.
    """
    start_dt, end_dt = season_date_range(season, start=start, end=end)
    leagues = _expand_leagues(league)
    results: list[PullResult] = []

    with make_client() as client:
        for lg in leagues:
            frame = _pull_league(
                league=lg,
                season=season,
                start=start_dt,
                end=end_dt,
                levels=levels,
                chunk_days=chunk_days,
                progress=progress,
                client=client,
            )
            out: Path | None = None
            if write:
                out = pitch_path(data_dir, season=season, league=lg)
                write_pitches(frame, out)
                logger.info("Wrote %s rows -> %s", len(frame), out)
            results.append(
                PullResult(
                    season=season,
                    league=lg,
                    start=start_dt,
                    end=end_dt,
                    rows=len(frame),
                    path=out,
                    frame=frame,
                )
            )
    return results


def _expand_leagues(league: LeagueChoice) -> list[str]:
    if league == "all":
        return ["mlb", "minors"]
    if league in {"mlb", "minors"}:
        return [league]
    raise ValueError(f"Unknown league={league!r}; expected mlb, minors, or all")


def _pull_league(
    *,
    league: str,
    season: int,
    start: date,
    end: date,
    levels: Sequence[str],
    chunk_days: int,
    progress: bool,
    client,
) -> pd.DataFrame:
    chunks = iter_date_chunks(start, end, chunk_days=chunk_days)
    frames: list[pd.DataFrame] = []
    iterator: Iterable[tuple[date, date]] = chunks
    if progress:
        iterator = tqdm(chunks, desc=f"{league} {season}", unit="chunk")

    for chunk_start, chunk_end in iterator:
        try:
            if league == "mlb":
                part = fetch_mlb_pitches(chunk_start, chunk_end, client=client)
            else:
                part = fetch_minors_pitches(
                    chunk_start,
                    chunk_end,
                    season=season,
                    levels=levels,
                    client=client,
                )
        except SavantError as exc:
            logger.warning(
                "Savant error for %s %s–%s: %s",
                league,
                chunk_start,
                chunk_end,
                exc,
            )
            continue
        except Exception as exc:  # noqa: BLE001 - keep long pulls resilient
            logger.warning(
                "Request failed for %s %s–%s: %s",
                league,
                chunk_start,
                chunk_end,
                exc,
            )
            continue
        if not part.empty:
            part = part.copy()
            part["season"] = season
            frames.append(part)

    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(
        subset=[
            c
            for c in ("game_pk", "at_bat_number", "pitch_number", "pitcher", "batter")
            if c in combined.columns
        ],
        keep="last",
    )
    return combined
