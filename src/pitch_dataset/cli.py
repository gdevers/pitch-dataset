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
    _add_sample_parser(sub)
    _add_train_parser(sub)
    _add_optimize_parser(sub)
    _add_traded_parser(sub)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if args.command == "pull":
        return _cmd_pull(args)
    if args.command == "sample":
        return _cmd_sample(args)
    if args.command == "train-model":
        return _cmd_train(args)
    if args.command == "optimize":
        return _cmd_optimize(args)
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
