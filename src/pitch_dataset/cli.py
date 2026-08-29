"""CLI for building the pitch dataset and optimizing arsenals."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from pitch_dataset.pipeline import pull_pitches
from pitch_dataset.savant import DEFAULT_MINOR_LEVELS
from pitch_dataset.seasons import DEFAULT_SEASON, SUPPORTED_SEASONS
from pitch_dataset.storage import pitch_path, read_pitches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pitch-dataset",
        description=(
            "Build a pitch-level MLB + MiLB Statcast dataset and optimize "
            f"pitch arsenals. Default season is {DEFAULT_SEASON}."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    _add_pull_parser(sub)
    _add_pull_api_parser(sub)
    _add_pull_fangraphs_parser(sub)
    _add_pull_register_parser(sub)
    _add_pull_all_parser(sub)
    _add_sample_parser(sub)
    _add_train_parser(sub)
    _add_train_select_parser(sub)
    _add_optimize_parser(sub)
    _add_select_parser(sub)
    _add_traded_parser(sub)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if args.command == "pull":
        return _cmd_pull(args)
    if args.command == "pull-api":
        return _cmd_pull_api(args)
    if args.command == "pull-fangraphs":
        return _cmd_pull_fangraphs(args)
    if args.command == "pull-register":
        return _cmd_pull_register(args)
    if args.command == "pull-all":
        return _cmd_pull_all(args)
    if args.command == "sample":
        return _cmd_sample(args)
    if args.command == "train-model":
        return _cmd_train(args)
    if args.command == "train-select":
        return _cmd_train_select(args)
    if args.command == "optimize":
        return _cmd_optimize(args)
    if args.command == "select":
        return _cmd_select(args)
    if args.command == "traded":
        return _cmd_traded(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def _add_pull_parser(sub: argparse._SubParsersAction) -> None:
    pull = sub.add_parser("pull", help="Pull pitches and write Parquet files")
    pull.add_argument(
        "--season",
        type=int,
        default=DEFAULT_SEASON,
        help=f"Season year (default: {DEFAULT_SEASON}; supported: {SUPPORTED_SEASONS})",
    )
    pull.add_argument(
        "--league",
        choices=("mlb", "minors", "all"),
        default="all",
        help="Which league(s) to pull (default: all)",
    )
    pull.add_argument("--start", type=str, default=None, help="YYYY-MM-DD override")
    pull.add_argument("--end", type=str, default=None, help="YYYY-MM-DD override")
    pull.add_argument(
        "--levels",
        type=str,
        default=",".join(DEFAULT_MINOR_LEVELS),
        help="Comma-separated MiLB levels (default: AAA,A)",
    )
    pull.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Output directory for Parquet files",
    )
    pull.add_argument(
        "--chunk-days",
        type=int,
        default=1,
        help="Date-range chunk size for Savant requests (default: 1)",
    )
    pull.add_argument(
        "--no-write",
        action="store_true",
        help="Skip writing Parquet (return counts only)",
    )


def _add_pull_api_parser(sub: argparse._SubParsersAction) -> None:
    pull_api = sub.add_parser(
        "pull-api",
        help="Pull MLB Stats API schedules, rosters, transactions, and lineups",
    )
    pull_api.add_argument("--season", type=int, default=DEFAULT_SEASON)
    pull_api.add_argument("--start", type=str, default=None, help="YYYY-MM-DD override")
    pull_api.add_argument("--end", type=str, default=None, help="YYYY-MM-DD override")
    pull_api.add_argument("--data-dir", type=str, default="data")
    pull_api.add_argument(
        "--skip-lineups",
        action="store_true",
        help="Skip per-game boxscore lineup pulls (faster)",
    )


def _add_pull_fangraphs_parser(sub: argparse._SubParsersAction) -> None:
    pull_fg = sub.add_parser(
        "pull-fangraphs",
        help="Pull FanGraphs batting/pitching leaderboards and platoon splits",
    )
    pull_fg.add_argument("--season", type=int, default=DEFAULT_SEASON)
    pull_fg.add_argument("--data-dir", type=str, default="data")
    pull_fg.add_argument(
        "--skip-splits",
        action="store_true",
        help="Skip platoon split leaderboards",
    )


def _add_pull_register_parser(sub: argparse._SubParsersAction) -> None:
    pull_reg = sub.add_parser(
        "pull-register",
        help="Download/cache the Chadwick player ID register",
    )
    pull_reg.add_argument("--data-dir", type=str, default="data")


def _add_pull_all_parser(sub: argparse._SubParsersAction) -> None:
    pull_all = sub.add_parser(
        "pull-all",
        help=(
            "Pull Savant pitches plus MLB API, FanGraphs, and Chadwick register "
            f"(default season {DEFAULT_SEASON})"
        ),
    )
    pull_all.add_argument("--season", type=int, default=DEFAULT_SEASON)
    pull_all.add_argument(
        "--league",
        choices=("mlb", "minors", "all"),
        default="mlb",
        help="Savant league(s) to pull (default: mlb)",
    )
    pull_all.add_argument("--start", type=str, default=None, help="YYYY-MM-DD override")
    pull_all.add_argument("--end", type=str, default=None, help="YYYY-MM-DD override")
    pull_all.add_argument("--data-dir", type=str, default="data")
    pull_all.add_argument(
        "--skip-savant",
        action="store_true",
        help="Skip Baseball Savant pitch pulls",
    )
    pull_all.add_argument(
        "--skip-lineups",
        action="store_true",
        help="Skip MLB API lineup boxscore pulls",
    )
    pull_all.add_argument(
        "--skip-splits",
        action="store_true",
        help="Skip FanGraphs platoon split pulls",
    )


def _add_sample_parser(sub: argparse._SubParsersAction) -> None:
    sample = sub.add_parser(
        "sample",
        help=f"Smoke-test a one-day {DEFAULT_SEASON} pull for MLB and minors",
    )
    sample.add_argument(
        "--date",
        type=str,
        default=None,
        help="Day to sample (YYYY-MM-DD). Default: 2026-04-15 (typical early-season slate).",
    )
    sample.add_argument("--data-dir", type=str, default="data")


def _add_train_parser(sub: argparse._SubParsersAction) -> None:
    train = sub.add_parser(
        "train-model",
        help="Train the pitch-outcome model used for arsenal optimization",
    )
    train.add_argument("--season", type=int, default=DEFAULT_SEASON)
    train.add_argument(
        "--league",
        choices=("mlb", "minors", "all"),
        default="mlb",
        help="Training league (default: mlb)",
    )
    train.add_argument("--data-dir", type=str, default="data")
    train.add_argument(
        "--model-path",
        type=str,
        default="models/outcome_model.joblib",
        help="Where to write the trained model",
    )
    train.add_argument(
        "--min-pitch-n",
        type=int,
        default=200,
        help="Minimum league-wide pitch-type count to include as a one-hot",
    )


def _add_train_select_parser(sub: argparse._SubParsersAction) -> None:
    train = sub.add_parser(
        "train-select",
        help="Train the situational pitch-selection outcome model",
    )
    train.add_argument("--season", type=int, default=DEFAULT_SEASON)
    train.add_argument(
        "--seasons",
        type=str,
        default=None,
        help="Comma-separated seasons to combine (e.g. 2025,2026)",
    )
    train.add_argument(
        "--league",
        choices=("mlb", "minors", "all"),
        default="mlb",
        help="Training league (default: mlb)",
    )
    train.add_argument("--data-dir", type=str, default="data")
    train.add_argument(
        "--model-path",
        type=str,
        default="models/situational_model.joblib",
        help="Where to write the trained situational model",
    )
    train.add_argument(
        "--min-pitch-n",
        type=int,
        default=200,
        help="Minimum league-wide pitch-type count to include as a one-hot",
    )


def _add_select_parser(sub: argparse._SubParsersAction) -> None:
    sel = sub.add_parser(
        "select",
        help="Recommend a pitch for a specific batter/count/situation",
    )
    sel.add_argument("--pitcher", type=str, default=None, help='Pitcher name or MLBAM id')
    sel.add_argument("--batter", type=str, default=None, help='Batter name or MLBAM id')
    sel.add_argument("--count", type=str, default=None, help='Count e.g. "1-2"')
    sel.add_argument(
        "--leverage",
        choices=("low", "medium", "high"),
        default=None,
        help="Leverage bucket override",
    )
    sel.add_argument("--outs", type=int, default=None)
    sel.add_argument("--stand", type=str, choices=("L", "R"), default=None)
    sel.add_argument("--p-throws", type=str, choices=("L", "R"), default=None)
    sel.add_argument("--runners-on", type=int, default=None)
    sel.add_argument("--score-diff", type=int, default=None)
    sel.add_argument("--prev-pitch", type=str, default=None)
    sel.add_argument("--tto", type=int, default=1)
    sel.add_argument("--season", type=int, default=DEFAULT_SEASON)
    sel.add_argument(
        "--seasons",
        type=str,
        default=None,
        help="Comma-separated seasons for training data context",
    )
    sel.add_argument(
        "--league",
        choices=("mlb", "minors", "all"),
        default="mlb",
    )
    sel.add_argument("--data-dir", type=str, default="data")
    sel.add_argument(
        "--model-path",
        type=str,
        default="models/situational_model.joblib",
    )
    sel.add_argument(
        "--report",
        type=str,
        default=None,
        help="Optional markdown report path",
    )
    sel.add_argument(
        "--html",
        type=str,
        default=None,
        help="Optional HTML visual path (single matchup)",
    )
    sel.add_argument(
        "--train",
        action="store_true",
        help="Train situational model before scoring",
    )
    sel.add_argument(
        "--train-if-missing",
        action="store_true",
        help="Train situational model if model-path does not exist",
    )
    sel.add_argument(
        "--demo",
        action="store_true",
        help="Run built-in demo matchups and write reports/situational_selection.html",
    )


def _add_optimize_parser(sub: argparse._SubParsersAction) -> None:
    opt = sub.add_parser(
        "optimize",
        help="Recommend pitch-usage changes for a pitcher (or top-N by volume)",
    )
    opt.add_argument(
        "--pitcher",
        type=str,
        default=None,
        help='MLBAM pitcher id or name substring, e.g. 656302 or "Cease"',
    )
    opt.add_argument(
        "--top",
        type=int,
        default=3,
        help="If --pitcher omitted, optimize the top-N pitchers by pitch count",
    )
    opt.add_argument("--season", type=int, default=DEFAULT_SEASON)
    opt.add_argument(
        "--league",
        choices=("mlb", "minors", "all"),
        default="mlb",
    )
    opt.add_argument("--data-dir", type=str, default="data")
    opt.add_argument(
        "--model-path",
        type=str,
        default="models/outcome_model.joblib",
    )
    opt.add_argument(
        "--report",
        type=str,
        default=None,
        help="Optional path to write a markdown report",
    )
    opt.add_argument(
        "--train-if-missing",
        action="store_true",
        help="Train the outcome model if model-path does not exist",
    )
    opt.add_argument("--min-pct", type=float, default=0.03)
    opt.add_argument("--max-pct", type=float, default=0.55)
    opt.add_argument("--max-shift", type=float, default=0.15)


def _add_traded_parser(sub: argparse._SubParsersAction) -> None:
    traded = sub.add_parser(
        "traded",
        help="Pre/post trade-deadline analysis for headline moved pitchers",
    )
    traded.add_argument(
        "--pitchers",
        type=str,
        default=None,
        help="Comma-separated keys or last names (default: top-5 deadline arms)",
    )
    traded.add_argument("--season", type=int, default=DEFAULT_SEASON)
    traded.add_argument(
        "--league",
        choices=("mlb", "minors", "all"),
        default="mlb",
    )
    traded.add_argument("--data-dir", type=str, default="data")
    traded.add_argument(
        "--report",
        type=str,
        default="reports/traded_pitchers.md",
        help="Markdown report path",
    )
    traded.add_argument(
        "--html",
        type=str,
        default="reports/traded_pitchers.html",
        help="Self-contained HTML visual path",
    )
    traded.add_argument(
        "--shape-html",
        type=str,
        default="reports/traded_pitchers_shape.html",
        help="Shape + pairing focused HTML visual (pitcher switcher)",
    )
    traded.add_argument(
        "--json",
        type=str,
        default=None,
        help="Optional JSON export of analysis payload",
    )


def _cmd_pull(args: argparse.Namespace) -> int:
    levels = [part.strip() for part in args.levels.split(",") if part.strip()]
    results = pull_pitches(
        season=args.season,
        league=args.league,
        start=args.start,
        end=args.end,
        levels=levels,
        data_dir=args.data_dir,
        chunk_days=args.chunk_days,
        write=not args.no_write,
    )
    for result in results:
        loc = result.path or "(not written)"
        print(
            f"{result.league} {result.season}: {result.rows:,} pitches "
            f"({result.start} → {result.end}) -> {loc}"
        )
    return 0


def _cmd_pull_api(args: argparse.Namespace) -> int:
    from pitch_dataset.mlb_api import make_client, pull_mlb_api
    from pitch_dataset.storage import mlb_api_path, write_parquet

    with make_client() as client:
        frames = pull_mlb_api(
            season=args.season,
            start=args.start,
            end=args.end,
            include_lineups=not args.skip_lineups,
            client=client,
        )
    for kind, frame in frames.items():
        path = mlb_api_path(args.data_dir, season=args.season, kind=kind)
        write_parquet(frame, path)
        print(f"mlb {kind} {args.season}: {len(frame):,} rows -> {path}")
    return 0


def _cmd_pull_fangraphs(args: argparse.Namespace) -> int:
    from pitch_dataset.fangraphs import make_client, pull_fangraphs
    from pitch_dataset.storage import fangraphs_path, write_parquet

    with make_client() as client:
        frames = pull_fangraphs(
            season=args.season,
            include_splits=not args.skip_splits,
            client=client,
        )
    for stat_type, frame in frames.items():
        path = fangraphs_path(args.data_dir, season=args.season, stat_type=stat_type)
        write_parquet(frame, path)
        print(f"fangraphs {stat_type} {args.season}: {len(frame):,} rows -> {path}")
    return 0


def _cmd_pull_register(args: argparse.Namespace) -> int:
    from pitch_dataset.chadwick import pull_chadwick_register
    from pitch_dataset.storage import chadwick_register_path, write_parquet

    frame = pull_chadwick_register()
    path = chadwick_register_path(args.data_dir)
    write_parquet(frame, path)
    print(f"chadwick register: {len(frame):,} rows -> {path}")
    return 0


def _cmd_pull_all(args: argparse.Namespace) -> int:
    if not args.skip_savant:
        pull_args = argparse.Namespace(
            season=args.season,
            league=args.league,
            start=args.start,
            end=args.end,
            levels=",".join(DEFAULT_MINOR_LEVELS),
            data_dir=args.data_dir,
            chunk_days=1,
            no_write=False,
        )
        _cmd_pull(pull_args)

    api_args = argparse.Namespace(
        season=args.season,
        start=args.start,
        end=args.end,
        data_dir=args.data_dir,
        skip_lineups=args.skip_lineups,
    )
    _cmd_pull_api(api_args)

    fg_args = argparse.Namespace(
        season=args.season,
        data_dir=args.data_dir,
        skip_splits=args.skip_splits,
    )
    _cmd_pull_fangraphs(fg_args)

    reg_args = argparse.Namespace(data_dir=args.data_dir)
    _cmd_pull_register(reg_args)
    return 0


def _cmd_sample(args: argparse.Namespace) -> int:
    sample_day = date.fromisoformat(args.date) if args.date else date(2026, 4, 15)
    results = pull_pitches(
        season=DEFAULT_SEASON,
        league="all",
        start=sample_day,
        end=sample_day,
        data_dir=args.data_dir,
        write=True,
    )
    for result in results:
        print(
            f"sample {result.league}: {result.rows:,} pitches on {sample_day} "
            f"-> {result.path}"
        )
    return 0


def _load_league_frames(args: argparse.Namespace):
    import pandas as pd

    leagues = ["mlb", "minors"] if args.league == "all" else [args.league]
    frames = []
    for lg in leagues:
        path = pitch_path(args.data_dir, season=args.season, league=lg)
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path}. Pull data first, e.g. "
                f"`uv run pitch-dataset pull --league {lg} --season {args.season}`"
            )
        frames.append(read_pitches(path))
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]


def _load_season_frames(
    data_dir: str,
    *,
    seasons: list[int],
    league: str,
):
    import pandas as pd

    leagues = ["mlb", "minors"] if league == "all" else [league]
    frames = []
    for season in seasons:
        for lg in leagues:
            path = pitch_path(data_dir, season=season, league=lg)
            if not path.exists():
                raise FileNotFoundError(
                    f"Missing {path}. Pull data first for season {season}."
                )
            frames.append(read_pitches(path))
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]


def _parse_seasons_arg(args: argparse.Namespace) -> list[int]:
    if getattr(args, "seasons", None):
        return [int(s.strip()) for s in args.seasons.split(",") if s.strip()]
    return [args.season]


def _cmd_train_select(args: argparse.Namespace) -> int:
    from pitch_dataset.situational import train_situational_model

    seasons = _parse_seasons_arg(args)
    pitches = _load_season_frames(
        args.data_dir, seasons=seasons, league=args.league
    )
    model, metrics = train_situational_model(
        pitches,
        model_path=args.model_path,
        data_dir=args.data_dir,
        season=seasons[-1],
        min_pitch_n=args.min_pitch_n,
    )
    print(json.dumps(metrics, indent=2))
    print(f"Wrote situational model -> {args.model_path}")
    print(f"Feature count: {len(model.feature_names)}")
    return 0


def _cmd_select(args: argparse.Namespace) -> int:
    from pitch_dataset.situational import (
        DEMO_MATCHUPS,
        format_situational_text,
        load_situational_model,
        recommend_pitch,
        train_situational_model,
        write_situational_html,
        write_situational_report,
    )

    seasons = _parse_seasons_arg(args)
    pitches = _load_season_frames(
        args.data_dir, seasons=seasons, league=args.league
    )
    model_path = Path(args.model_path)
    if args.train or (args.train_if_missing and not model_path.exists()):
        logging.info("Training situational model at %s", model_path)
        model, _ = train_situational_model(
            pitches,
            model_path=model_path,
            data_dir=args.data_dir,
            season=seasons[-1],
        )
    elif not model_path.exists():
        raise FileNotFoundError(
            f"Missing model at {model_path}. Run "
            "`uv run pitch-dataset train-select` or pass --train / --train-if-missing."
        )
    else:
        model = load_situational_model(model_path)

    date_min = str(pitches["game_date"].min())[:10] if "game_date" in pitches.columns else "?"
    date_max = str(pitches["game_date"].max())[:10] if "game_date" in pitches.columns else "?"
    season_label = ",".join(str(s) for s in seasons)
    data_note = (
        f"_Situational model scored on {args.league.upper()} {season_label} pitches "
        f"({date_min} → {date_max}, n={len(pitches):,}). "
        "Micro pitch-choice (not season usage optimization)._"
    )

    rec_kwargs = {
        "leverage": args.leverage,
        "outs": args.outs,
        "stand": args.stand,
        "p_throws": args.p_throws,
        "runners_on": args.runners_on,
        "score_diff": args.score_diff,
        "prev_pitch": args.prev_pitch,
        "tto": args.tto,
        "data_dir": args.data_dir,
        "season": seasons[-1],
    }

    if args.demo:
        from pitch_dataset.situational import generate_demo_grid

        recs = []
        for spec in DEMO_MATCHUPS:
            try:
                rec = recommend_pitch(
                    pitches,
                    model,
                    pitcher=spec["pitcher"],
                    batter=spec["batter"],
                    count=spec["count"],
                    leverage=spec.get("leverage"),
                    outs=spec.get("outs"),
                    stand=spec.get("stand"),
                    p_throws=spec.get("p_throws"),
                    runners_on=spec.get("runners_on"),
                    score_diff=spec.get("score_diff"),
                    prev_pitch=spec.get("prev_pitch"),
                    tto=spec.get("tto", args.tto),
                    data_dir=args.data_dir,
                    season=seasons[-1],
                )
                recs.append(rec)
                print(format_situational_text(rec))
                print()
            except ValueError as exc:
                logging.warning("Skipping demo %s: %s", spec.get("label"), exc)
        if not recs:
            raise SystemExit("No demo matchups could be scored.")

        logging.info("Precomputing interactive demo grid (pitcher × batter × count × leverage × platoon)...")
        lookup, pools = generate_demo_grid(
            pitches,
            model,
            data_dir=args.data_dir,
            season=seasons[-1],
        )
        logging.info("Grid entries: %d pitchers=%d batters=%d", len(lookup), len(pools["pitchers"]), len(pools["batters"]))

        html_path = args.html or "reports/situational_selection.html"
        write_situational_html(
            recs,
            html_path,
            data_note=data_note,
            lookup=lookup,
            pools=pools,
        )
        report_path = args.report or "reports/situational_selection.md"
        write_situational_report(recs, report_path, data_note=data_note)
        print(f"Wrote report -> {report_path}", file=sys.stderr)
        print(f"Wrote HTML -> {html_path} ({len(lookup)} grid entries)", file=sys.stderr)
        return 0

    if not args.pitcher or not args.batter or not args.count:
        raise SystemExit("--pitcher, --batter, and --count are required unless --demo is set.")

    rec = recommend_pitch(
        pitches,
        model,
        pitcher=args.pitcher,
        batter=args.batter,
        count=args.count,
        **rec_kwargs,
    )
    print(format_situational_text(rec))
    if args.report:
        out = write_situational_report(rec, args.report, data_note=data_note)
        print(f"Wrote report -> {out}", file=sys.stderr)
    if args.html:
        out = write_situational_html([rec], args.html, data_note=data_note)
        print(f"Wrote HTML -> {out}", file=sys.stderr)
    return 0


def _cmd_train(args: argparse.Namespace) -> int:
    from pitch_dataset.arsenal import train_outcome_model

    pitches = _load_league_frames(args)
    model, metrics = train_outcome_model(
        pitches,
        model_path=args.model_path,
        min_pitch_n=args.min_pitch_n,
    )
    print(json.dumps(metrics, indent=2))
    print(f"Wrote model -> {args.model_path}")
    print(f"Feature count: {len(model.feature_names)}")
    return 0


def _cmd_optimize(args: argparse.Namespace) -> int:
    from pitch_dataset.arsenal import (
        format_recommendation_report,
        load_outcome_model,
        optimize_pitcher,
        optimize_pitchers,
        train_outcome_model,
        write_recommendation_report,
    )

    pitches = _load_league_frames(args)
    model_path = Path(args.model_path)
    if not model_path.exists():
        if args.train_if_missing:
            logging.info("Model missing; training at %s", model_path)
            model, _ = train_outcome_model(pitches, model_path=model_path)
        else:
            raise FileNotFoundError(
                f"Missing model at {model_path}. Run "
                "`uv run pitch-dataset train-model` or pass --train-if-missing."
            )
    else:
        model = load_outcome_model(model_path)

    date_min = str(pitches["game_date"].min())[:10] if "game_date" in pitches.columns else "?"
    date_max = str(pitches["game_date"].max())[:10] if "game_date" in pitches.columns else "?"
    data_note = (
        f"_Trained/scored on {args.league.upper()} {args.season} pitches "
        f"({date_min} → {date_max}, n={len(pitches):,}). "
        "Parquet data is local/gitignored; model artifact may be committed._"
    )

    kwargs = {
        "min_pct": args.min_pct,
        "max_pct": args.max_pct,
        "max_shift": args.max_shift,
    }
    if args.pitcher:
        recs = [optimize_pitcher(pitches, model, pitcher=args.pitcher, **kwargs)]
    else:
        recs = optimize_pitchers(pitches, model, top_n=args.top, **kwargs)

    report = format_recommendation_report(recs, data_note=data_note)
    print(report)
    if args.report:
        out = write_recommendation_report(recs, args.report, data_note=data_note)
        print(f"Wrote report -> {out}", file=sys.stderr)
    return 0


def _cmd_traded(args: argparse.Namespace) -> int:
    from pitch_dataset.traded_analysis import (
        analyze_traded_pitchers,
        format_traded_report,
        write_traded_html,
        write_traded_json,
        write_traded_report,
        write_traded_shape_html,
    )

    pitches = _load_league_frames(args)
    keys = None
    if args.pitchers:
        keys = [part.strip() for part in args.pitchers.split(",") if part.strip()]

    analyses = analyze_traded_pitchers(pitches, keys=keys)
    if not analyses:
        raise SystemExit("No matching traded pitchers found in the dataset.")

    date_min = str(pitches["game_date"].min())[:10] if "game_date" in pitches.columns else "?"
    date_max = str(pitches["game_date"].max())[:10] if "game_date" in pitches.columns else "?"
    data_note = (
        f"_MLB {args.season} pitches ({date_min} → {date_max}, n={len(pitches):,}). "
        "Team affiliation derived from `inning_topbot` + home/away. "
        "Post-trade samples are partial through data end date._"
    )

    report = format_traded_report(analyses, data_note=data_note)
    print(report)
    out_md = write_traded_report(analyses, args.report, data_note=data_note)
    out_html = write_traded_html(analyses, args.html, data_note=data_note)
    out_shape_html = write_traded_shape_html(analyses, args.shape_html, data_note=data_note)
    print(f"Wrote report -> {out_md}", file=sys.stderr)
    print(f"Wrote HTML -> {out_html}", file=sys.stderr)
    print(f"Wrote shape HTML -> {out_shape_html}", file=sys.stderr)
    if args.json:
        out_json = write_traded_json(analyses, args.json)
        print(f"Wrote JSON -> {out_json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
