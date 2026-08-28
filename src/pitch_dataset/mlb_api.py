"""MLB Stats API client for schedules, rosters, transactions, and lineups."""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd

from pitch_dataset.seasons import season_date_range

logger = logging.getLogger(__name__)

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
USER_AGENT = (
    "pitch-dataset/0.2 (+https://github.com/gdevers/pitch-dataset; research use)"
)
DEFAULT_SLEEP_SEC = 0.25


class MlbApiError(RuntimeError):
    """Raised when the MLB Stats API returns an unexpected payload."""


def make_client(timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=timeout,
        follow_redirects=True,
    )


def pull_mlb_api(
    *,
    season: int,
    start: date | str | None = None,
    end: date | str | None = None,
    include_lineups: bool = True,
    sleep_sec: float = DEFAULT_SLEEP_SEC,
    client: httpx.Client | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch schedule, transactions, rosters, and optional lineups for a season."""
    start_dt, end_dt = season_date_range(season, start=start, end=end)
    owns_client = client is None
    http = client or make_client()
    try:
        games = fetch_schedule(
            start_dt, end_dt, season=season, client=http, sleep_sec=sleep_sec
        )
        transactions = fetch_transactions(
            start_dt, end_dt, client=http, sleep_sec=sleep_sec
        )
        rosters = fetch_all_rosters(season=season, client=http, sleep_sec=sleep_sec)
        frames: dict[str, pd.DataFrame] = {
            "games": games,
            "transactions": transactions,
            "rosters": rosters,
        }
        if include_lineups and not games.empty:
            completed = games.loc[
                games["status"].astype(str).str.contains("Final", case=False, na=False),
                "game_pk",
            ].tolist()
            frames["lineups"] = fetch_lineups(
                completed,
                client=http,
                sleep_sec=sleep_sec,
            )
        else:
            frames["lineups"] = pd.DataFrame()
        return frames
    finally:
        if owns_client:
            http.close()


def fetch_schedule(
    start: date,
    end: date,
    *,
    season: int,
    client: httpx.Client,
    sleep_sec: float = DEFAULT_SLEEP_SEC,
) -> pd.DataFrame:
    """Pull game metadata for an inclusive date range."""
    rows: list[dict[str, Any]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=13), end)
        params = {
            "sportId": 1,
            "startDate": cursor.isoformat(),
            "endDate": chunk_end.isoformat(),
            "season": season,
            "gameType": "R,F,D,L,W,C,P",
            "hydrate": "team,venue",
        }
        payload = _get_json(f"{MLB_API_BASE}/schedule", params, client=client)
        for day in payload.get("dates", []):
            for game in day.get("games", []):
                rows.append(_parse_schedule_game(game, season=season))
        time.sleep(sleep_sec)
        cursor = chunk_end + timedelta(days=1)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.drop_duplicates(subset=["game_pk"], keep="last").reset_index(drop=True)


def fetch_transactions(
    start: date,
    end: date,
    *,
    client: httpx.Client,
    sleep_sec: float = DEFAULT_SLEEP_SEC,
) -> pd.DataFrame:
    """Pull league transactions for an inclusive date range."""
    params = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "sportId": 1,
    }
    payload = _get_json(f"{MLB_API_BASE}/transactions", params, client=client)
    time.sleep(sleep_sec)
    rows: list[dict[str, Any]] = []
    for txn in payload.get("transactions", []):
        person = txn.get("person") or {}
        team = txn.get("team") or {}
        rows.append(
            {
                "transaction_id": txn.get("id"),
                "date": txn.get("date"),
                "effective_date": txn.get("effectiveDate"),
                "type_code": txn.get("typeCode"),
                "type_desc": txn.get("typeDesc"),
                "description": txn.get("description"),
                "player_id": person.get("id"),
                "player_name": person.get("fullName"),
                "team_id": team.get("id"),
                "team_name": team.get("name"),
                "from_team_id": (txn.get("fromTeam") or {}).get("id"),
                "from_team_name": (txn.get("fromTeam") or {}).get("name"),
            }
        )
    return pd.DataFrame(rows)


def fetch_all_rosters(
    *,
    season: int,
    client: httpx.Client,
    sleep_sec: float = DEFAULT_SLEEP_SEC,
) -> pd.DataFrame:
    """Pull 40-man rosters for all MLB teams in a season."""
    teams_payload = _get_json(f"{MLB_API_BASE}/teams", {"season": season, "sportId": 1}, client=client)
    time.sleep(sleep_sec)
    rows: list[dict[str, Any]] = []
    for team in teams_payload.get("teams", []):
        team_id = team.get("id")
        if team_id is None:
            continue
        roster_payload = _get_json(
            f"{MLB_API_BASE}/teams/{team_id}/roster",
            {"season": season, "rosterType": "40Man"},
            client=client,
        )
        time.sleep(sleep_sec)
        for entry in roster_payload.get("roster", []):
            person = entry.get("person") or {}
            position = entry.get("position") or {}
            rows.append(
                {
                    "season": season,
                    "team_id": team_id,
                    "team_name": team.get("name"),
                    "team_abbr": team.get("abbreviation"),
                    "player_id": person.get("id"),
                    "player_name": person.get("fullName"),
                    "jersey_number": entry.get("jerseyNumber"),
                    "position_code": position.get("code"),
                    "position_name": position.get("name"),
                    "status_code": (entry.get("status") or {}).get("code"),
                    "status_desc": (entry.get("status") or {}).get("description"),
                }
            )
    return pd.DataFrame(rows)


def fetch_lineups(
    game_pks: list[int],
    *,
    client: httpx.Client,
    sleep_sec: float = DEFAULT_SLEEP_SEC,
    progress: bool = True,
) -> pd.DataFrame:
    """Pull starting lineups and positions from completed game boxscores."""
    from tqdm import tqdm

    rows: list[dict[str, Any]] = []
    iterator: Any = game_pks
    if progress and len(game_pks) > 10:
        iterator = tqdm(game_pks, desc="lineups", unit="game")

    for game_pk in iterator:
        try:
            payload = _get_json(f"{MLB_API_BASE}/game/{game_pk}/boxscore", {}, client=client)
        except MlbApiError as exc:
            logger.warning("Boxscore unavailable for game_pk=%s: %s", game_pk, exc)
            time.sleep(sleep_sec)
            continue
        game_date = (payload.get("game") or {}).get("officialDate")
        for side, is_home in (("away", False), ("home", True)):
            team_block = (payload.get("teams") or {}).get(side) or {}
            team = team_block.get("team") or {}
            players = team_block.get("players") or {}
            for player_key, player_info in players.items():
                person = player_info.get("person") or {}
                batting_order = player_info.get("battingOrder")
                position = player_info.get("position") or {}
                if batting_order is None and position.get("type") != "Pitcher":
                    continue
                rows.append(
                    {
                        "game_pk": game_pk,
                        "game_date": game_date,
                        "team_id": team.get("id"),
                        "team_name": team.get("name"),
                        "is_home": is_home,
                        "player_id": person.get("id"),
                        "player_name": person.get("fullName"),
                        "batting_order": batting_order,
                        "position_code": position.get("code"),
                        "position_name": position.get("name"),
                        "is_starter": batting_order is not None,
                    }
                )
        time.sleep(sleep_sec)
    return pd.DataFrame(rows)


def _parse_schedule_game(game: dict[str, Any], *, season: int) -> dict[str, Any]:
    teams = game.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    venue = game.get("venue") or {}
    return {
        "season": season,
        "game_pk": game.get("gamePk"),
        "game_date": game.get("officialDate") or game.get("gameDate", "")[:10],
        "game_type": game.get("gameType"),
        "status": (game.get("status") or {}).get("detailedState"),
        "status_code": (game.get("status") or {}).get("statusCode"),
        "home_team_id": (home.get("team") or {}).get("id"),
        "home_team": (home.get("team") or {}).get("name"),
        "home_team_abbr": (home.get("team") or {}).get("abbreviation"),
        "away_team_id": (away.get("team") or {}).get("id"),
        "away_team": (away.get("team") or {}).get("name"),
        "away_team_abbr": (away.get("team") or {}).get("abbreviation"),
        "home_score": home.get("score"),
        "away_score": away.get("score"),
        "venue_id": venue.get("id"),
        "venue_name": venue.get("name"),
        "doubleheader": game.get("doubleHeader"),
        "game_number": game.get("gameNumber"),
        "day_night": game.get("dayNight"),
    }


def _get_json(url: str, params: dict[str, Any], *, client: httpx.Client) -> dict[str, Any]:
    response = client.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise MlbApiError(f"Expected JSON object from {url}")
    return payload
