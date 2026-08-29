"""Local web server for situational pitch selection with live model inference."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pitch_dataset.situational import (
    STANDARD_COUNTS,
    load_situational_model,
    prepare_situational_pitches,
    recommend_pitch,
    recommendation_to_dict,
)
from pitch_dataset.storage import pitch_path, read_pitches

STATIC_DIR = Path(__file__).resolve().parent / "static" / "situational_web"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


@dataclass
class WebState:
    model: Any
    pitches: pd.DataFrame
    prepared: pd.DataFrame
    pitchers: list[dict[str, Any]]
    batters: list[dict[str, Any]]
    data_note: str
    data_dir: Path
    season: int


def _player_name_from_register(
    player_id: int, register: pd.DataFrame
) -> str | None:
    row = register[register["key_mlbam"] == player_id]
    if row.empty:
        return None
    r = row.iloc[0]
    return f"{r['name_first']} {r['name_last']}"


def build_pitcher_roster(
    prepared: pd.DataFrame, data_dir: Path | str
) -> list[dict[str, Any]]:
    """All pitchers in the pitch parquet with MLBAM id, name, handedness, pitch count."""
    from pitch_dataset.situational import _chadwick_register

    register = _chadwick_register(Path(data_dir))
    grouped = (
        prepared.groupby("pitcher", as_index=False)
        .agg(
            n=("pitcher", "size"),
            p_throws=("p_throws", lambda s: s.mode().iloc[0] if len(s) else "R"),
            player_name=("player_name", "first"),
        )
        .sort_values("n", ascending=False)
    )
    roster: list[dict[str, Any]] = []
    for _, row in grouped.iterrows():
        pid = int(row["pitcher"])
        name = _player_name_from_register(pid, register) or str(row["player_name"] or pid)
        roster.append(
            {
                "id": pid,
                "name": name,
                "label": name,
                "p_throws": str(row["p_throws"] or "R").upper(),
                "n_pitches": int(row["n"]),
            }
        )
    return roster


def build_batter_roster(
    prepared: pd.DataFrame, data_dir: Path | str
) -> list[dict[str, Any]]:
    """All batters in the pitch parquet with MLBAM id, name, stand, pitch count."""
    from pitch_dataset.situational import _chadwick_register

    register = _chadwick_register(Path(data_dir))
    grouped = (
        prepared.groupby("batter", as_index=False)
        .agg(
            n=("batter", "size"),
            stand=("stand", lambda s: s.mode().iloc[0] if len(s) else "R"),
        )
        .sort_values("n", ascending=False)
    )
    roster: list[dict[str, Any]] = []
    for _, row in grouped.iterrows():
        bid = int(row["batter"])
        name = _player_name_from_register(bid, register) or str(bid)
        roster.append(
            {
                "id": bid,
                "name": name,
                "label": name,
                "stand": str(row["stand"] or "R").upper(),
                "n_pitches": int(row["n"]),
            }
        )
    return roster


def _filter_roster(
    roster: list[dict[str, Any]], q: str | None, limit: int | None
) -> list[dict[str, Any]]:
    if q:
        needle = q.strip().lower()
        filtered = [
            p
            for p in roster
            if needle in p["name"].lower() or needle in str(p["id"])
        ]
    else:
        filtered = roster
    if limit is not None and limit > 0:
        return filtered[:limit]
    return filtered


def load_web_state(
    *,
    data_dir: str = "data",
    season: int = 2026,
    league: str = "mlb",
    model_path: str = "models/situational_model.joblib",
) -> WebState:
    leagues = ["mlb", "minors"] if league == "all" else [league]
    frames: list[pd.DataFrame] = []
    for lg in leagues:
        path = pitch_path(data_dir, season=season, league=lg)
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path}. Pull data first, e.g. "
                f"`uv run pitch-dataset pull --league {lg} --season {season}`"
            )
        frames.append(read_pitches(path))
    pitches = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    model_file = Path(model_path)
    if not model_file.exists():
        raise FileNotFoundError(
            f"Missing model at {model_file}. Run "
            "`uv run pitch-dataset train-select` first."
        )

    prepared = prepare_situational_pitches(pitches, data_dir=data_dir, season=season)
    model = load_situational_model(model_path)

    date_min = (
        str(pitches["game_date"].min())[:10] if "game_date" in pitches.columns else "?"
    )
    date_max = (
        str(pitches["game_date"].max())[:10] if "game_date" in pitches.columns else "?"
    )
    league_label = league.upper()
    data_note = (
        f"Situational model scored on {league_label} {season} pitches "
        f"({date_min} → {date_max}, n={len(pitches):,}). "
        "Live inference — micro pitch-choice (not season usage optimization)."
    )

    return WebState(
        model=model,
        pitches=pitches,
        prepared=prepared,
        pitchers=build_pitcher_roster(prepared, data_dir),
        batters=build_batter_roster(prepared, data_dir),
        data_note=data_note,
        data_dir=Path(data_dir),
        season=season,
    )


def create_app(state: WebState) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.web = state
        yield

    app = FastAPI(title="Situational Pitch Selection", lifespan=lifespan)

    @app.get("/api/meta")
    def api_meta() -> dict[str, Any]:
        return {
            "data_note": state.data_note,
            "counts": STANDARD_COUNTS,
            "leverage_levels": ["low", "medium", "high"],
            "n_pitchers": len(state.pitchers),
            "n_batters": len(state.batters),
            "season": state.season,
        }

    @app.get("/api/pitchers")
    def api_pitchers(
        q: str | None = Query(None, description="Name or MLBAM id substring"),
        limit: int | None = Query(None, ge=1, le=5000),
    ) -> list[dict[str, Any]]:
        return _filter_roster(state.pitchers, q, limit)

    @app.get("/api/batters")
    def api_batters(
        q: str | None = Query(None, description="Name or MLBAM id substring"),
        limit: int | None = Query(None, ge=1, le=5000),
    ) -> list[dict[str, Any]]:
        return _filter_roster(state.batters, q, limit)

    @app.get("/api/recommend")
    def api_recommend(
        pitcher_id: int | None = Query(None),
        batter_id: int | None = Query(None),
        pitcher: str | None = Query(None, description="Pitcher name (fuzzy match)"),
        batter: str | None = Query(None, description="Batter name (fuzzy match)"),
        count: str = Query(..., description='Count e.g. "1-2"'),
        leverage: str | None = Query(None, pattern="^(low|medium|high)$"),
        stand: str | None = Query(None, pattern="^[LR]$"),
        p_throws: str | None = Query(None, alias="p_throws", pattern="^[LR]$"),
        outs: int | None = Query(None, ge=0, le=2),
        runners_on: int | None = Query(None, ge=0, le=3, alias="runners_on"),
        score_diff: int | None = Query(None, alias="score_diff"),
        prev_pitch: str | None = Query(None, alias="prev_pitch"),
        tto: int = Query(1, ge=1, le=3),
    ) -> dict[str, Any]:
        pid = pitcher_id
        bid = batter_id
        if pid is None and pitcher:
            pid = pitcher
        if bid is None and batter:
            bid = batter
        if pid is None or bid is None:
            raise HTTPException(
                status_code=400,
                detail="Provide pitcher_id/batter_id or pitcher/batter name params.",
            )
        try:
            rec = recommend_pitch(
                state.pitches,
                state.model,
                pitcher=pid,
                batter=bid,
                count=count,
                leverage=leverage,
                outs=outs,
                stand=stand,
                p_throws=p_throws,
                runners_on=runners_on,
                score_diff=score_diff,
                prev_pitch=prev_pitch,
                tto=tto,
                data_dir=state.data_dir,
                season=state.season,
                prepared=state.prepared,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return recommendation_to_dict(rec)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


def run_select_web(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    data_dir: str = "data",
    season: int = 2026,
    league: str = "mlb",
    model_path: str = "models/situational_model.joblib",
) -> None:
    import uvicorn

    logging.info("Loading pitch data and situational model...")
    state = load_web_state(
        data_dir=data_dir,
        season=season,
        league=league,
        model_path=model_path,
    )
    app = create_app(state)
    url = f"http://{host}:{port}/"
    print(f"Situational pitch selection server ready")
    print(f"  Open in browser: {url}")
    print(f"  Pitchers: {len(state.pitchers):,}  Batters: {len(state.batters):,}")
    print(f"  {state.data_note}")
    uvicorn.run(app, host=host, port=port, log_level="info")
