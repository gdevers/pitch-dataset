"""Baseball Savant CSV clients for MLB and MiLB pitch-level Statcast."""

from __future__ import annotations

import io
import logging
from datetime import date
from typing import Iterable, Literal
from urllib.parse import urlencode

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

MLB_CSV_URL = "https://baseballsavant.mlb.com/statcast_search/csv"
MINORS_CSV_URL = "https://baseballsavant.mlb.com/statcast-search-minors/csv"

# Savant MiLB search officially documents A and AAA tracking coverage.
DEFAULT_MINOR_LEVELS: tuple[str, ...] = ("AAA", "A")
ALL_MINOR_LEVELS: tuple[str, ...] = ("AAA", "AA", "A+", "A", "Rookie")

League = Literal["mlb", "minors"]

USER_AGENT = (
    "pitch-dataset/0.1 (+https://github.com/local/pitch-dataset; research use)"
)


class SavantError(RuntimeError):
    """Raised when Baseball Savant returns an error payload or HTTP failure."""


def fetch_mlb_pitches(
    start: date,
    end: date,
    *,
    client: httpx.Client | None = None,
    game_types: Iterable[str] = ("R", "PO", "F", "D", "L", "W", "C"),
) -> pd.DataFrame:
    """Pull MLB Statcast pitch rows for an inclusive date range."""
    params = {
        "all": "true",
        "hfPT": "",
        "hfAB": "",
        "hfGT": _pipe(game_types),
        "hfSea": "",
        "hfSit": "",
        "player_type": "pitcher",
        "hfOuts": "",
        "opponent": "",
        "pitcher_throws": "",
        "batter_stands": "",
        "hfSA": "",
        "game_date_gt": start.isoformat(),
        "game_date_lt": end.isoformat(),
        "team": "",
        "position": "",
        "hfRO": "",
        "home_road": "",
        "hfFlag": "",
        "hfInn": "",
        "min_pitches": "0",
        "min_results": "0",
        "group_by": "name",
        "sort_col": "pitches",
        "player_event_sort": "h_launch_speed",
        "sort_order": "desc",
        "min_abs": "0",
        "type": "details",
    }
    return _get_csv(MLB_CSV_URL, params, client=client, league="mlb")


def fetch_minors_pitches(
    start: date,
    end: date,
    *,
    season: int,
    levels: Iterable[str] = DEFAULT_MINOR_LEVELS,
    client: httpx.Client | None = None,
    game_types: Iterable[str] = ("R", "PO"),
) -> pd.DataFrame:
    """Pull MiLB Statcast pitch rows for an inclusive date range."""
    level_list = [str(level).strip() for level in levels if str(level).strip()]
    params = {
        "all": "true",
        "player_type": "pitcher",
        "hfSea": _pipe([str(season)]),
        "hfGT": _pipe(game_types),
        "game_date_gt": start.isoformat(),
        "game_date_lt": end.isoformat(),
        "hfMo": "",
        "hfLevel": _pipe(level_list) if level_list else "",
        "hfFlag": r"is\.\.tracked|",
        "chk_is..tracked": "on",
        "minors": "true",
        "type": "details",
        "min_pitches": "0",
        "min_results": "0",
        "group_by": "name",
        "sort_col": "pitches",
        "sort_order": "desc",
    }
    return _get_csv(MINORS_CSV_URL, params, client=client, league="minors")


def make_client(timeout: float = 120.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "text/csv,*/*"},
        timeout=timeout,
        follow_redirects=True,
    )


def _pipe(values: Iterable[str]) -> str:
    items = [str(v) for v in values if str(v)]
    if not items:
        return ""
    return "|".join(items) + "|"


def _get_csv(
    url: str,
    params: dict[str, str],
    *,
    client: httpx.Client | None,
    league: League,
) -> pd.DataFrame:
    owns_client = client is None
    http = client or make_client()
    try:
        logger.debug("GET %s?%s", url, urlencode(params))
        response = http.get(url, params=params)
        response.raise_for_status()
        text = response.text.strip()
        if not text:
            return pd.DataFrame()
        if text.lower().startswith("<!doctype html") or text.lower().startswith(
            "<html"
        ):
            raise SavantError(
                f"Savant returned HTML instead of CSV for {league} "
                f"({params.get('game_date_gt')}–{params.get('game_date_lt')})."
            )
        frame = pd.read_csv(io.StringIO(text), low_memory=False)
        if "error" in frame.columns and not frame.empty:
            raise SavantError(str(frame["error"].iloc[0]))
        if frame.empty:
            return frame
        frame = frame.copy()
        frame["league"] = league
        return frame
    finally:
        if owns_client:
            http.close()
