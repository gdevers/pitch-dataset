"""FanGraphs season stats and platoon splits."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Literal

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

FG_API_URL = "https://www.fangraphs.com/api/leaders/major-league/data"
USER_AGENT = (
    "pitch-dataset/0.3 (+https://github.com/gdevers/pitch-dataset; research use)"
)
DEFAULT_SLEEP_SEC = 0.5
PAGE_SIZE = 200

StatsKind = Literal["bat", "pit"]
HandSplit = Literal["", "L", "R"]


def pull_fangraphs(
    *,
    season: int,
    include_splits: bool = True,
    sleep_sec: float = DEFAULT_SLEEP_SEC,
    client: httpx.Client | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch FanGraphs batting/pitching leaderboards for a season."""
    owns_client = client is None
    http = client or make_client()
    try:
        frames: dict[str, pd.DataFrame] = {}
        for stat_type, stats in (("batting", "bat"), ("pitching", "pit")):
            try:
                frame = fetch_leaderboard(
                    season,
                    stats=stats,  # type: ignore[arg-type]
                    hand="",
                    client=http,
                    sleep_sec=sleep_sec,
                )
                frames[stat_type] = _normalize_fangraphs_frame(
                    frame, season=season, stat_type=stat_type
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("FanGraphs %s stats failed for %s: %s", stat_type, season, exc)
                frames[stat_type] = pd.DataFrame()

        if include_splits:
            frames["batting_splits"] = _fetch_platoon_frame(
                season,
                stats="bat",
                client=http,
                sleep_sec=sleep_sec,
                stat_type="batting",
            )
            frames["pitching_splits"] = _fetch_platoon_frame(
                season,
                stats="pit",
                client=http,
                sleep_sec=sleep_sec,
                stat_type="pitching",
            )
        else:
            frames["batting_splits"] = pd.DataFrame()
            frames["pitching_splits"] = pd.DataFrame()
        return frames
    finally:
        if owns_client:
            http.close()


def make_client(timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=timeout,
        follow_redirects=True,
    )


def fetch_leaderboard(
    season: int,
    *,
    stats: StatsKind,
    hand: HandSplit = "",
    qual: int = 1,
    client: httpx.Client,
    sleep_sec: float = DEFAULT_SLEEP_SEC,
) -> pd.DataFrame:
    """Paginate the FanGraphs JSON leaderboard API."""
    rows: list[dict[str, Any]] = []
    page = 1
    total_count: int | None = None

    while True:
        params = {
            "age": "",
            "pos": "all",
            "stats": stats,
            "lg": "all",
            "qual": str(qual),
            "season": str(season),
            "season1": str(season),
            "startdate": "",
            "enddate": "",
            "month": "0",
            "hand": hand,
            "team": "0",
            "pageitems": str(PAGE_SIZE),
            "pagenum": str(page),
        }
        response = client.get(FG_API_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("data") or []
        total_count = payload.get("totalCount", total_count)
        if not batch:
            break
        rows.extend(batch)
        if total_count is not None and len(rows) >= total_count:
            break
        page += 1
        time.sleep(sleep_sec)

    return pd.DataFrame(rows)


def _fetch_platoon_frame(
    season: int,
    *,
    stats: StatsKind,
    client: httpx.Client,
    sleep_sec: float,
    stat_type: str,
) -> pd.DataFrame:
    try:
        vs_left = fetch_leaderboard(
            season, stats=stats, hand="L", client=client, sleep_sec=sleep_sec
        )
        vs_right = fetch_leaderboard(
            season, stats=stats, hand="R", client=client, sleep_sec=sleep_sec
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("FanGraphs %s platoon splits failed for %s: %s", stat_type, season, exc)
        return pd.DataFrame()
    return _combine_split_frames(vs_left, vs_right, season=season, stat_type=stat_type)


def _combine_split_frames(
    vs_left: pd.DataFrame,
    vs_right: pd.DataFrame,
    *,
    season: int,
    stat_type: str,
) -> pd.DataFrame:
    if vs_left.empty and vs_right.empty:
        return pd.DataFrame()

    left = _normalize_fangraphs_frame(vs_left, season=season, stat_type=stat_type)
    right = _normalize_fangraphs_frame(vs_right, season=season, stat_type=stat_type)
    id_col = "IDfg"
    if id_col not in left.columns or id_col not in right.columns:
        return pd.DataFrame()

    meta_cols = {
        id_col,
        "season",
        "stat_type",
        "player_name",
        "Team",
        "xMLBAMID",
        "split_type",
    }
    stat_cols = [c for c in left.columns if c not in meta_cols]
    left = left.rename(columns={c: f"{c}_vs_l" for c in stat_cols})
    right = right.rename(columns={c: f"{c}_vs_r" for c in stat_cols})
    merged = left.merge(
        right[[id_col] + [f"{c}_vs_r" for c in stat_cols]],
        on=id_col,
        how="outer",
    )
    merged["split_type"] = "platoon"
    return merged


def _normalize_fangraphs_frame(
    frame: pd.DataFrame,
    *,
    season: int,
    stat_type: str,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out["season"] = season
    out["stat_type"] = stat_type
    if "playerid" in out.columns and "IDfg" not in out.columns:
        out = out.rename(columns={"playerid": "IDfg"})
    if "Name" in out.columns:
        out["player_name"] = out["Name"].map(_strip_html)
    return out


def _strip_html(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value)
    return re.sub(r"<[^>]+>", "", text).strip()
