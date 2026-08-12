"""CLI for building the pitch dataset."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from pitch_dataset.pipeline import pull_pitches
from pitch_dataset.savant import DEFAULT_MINOR_LEVELS
from pitch_dataset.seasons import DEFAULT_SEASON, SUPPORTED_SEASONS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pitch-dataset",
        description=(
            "Build a pitch-level MLB + MiLB Statcast dataset. "
            f"Default season is {DEFAULT_SEASON}."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    sub = parser.add_subparsers(dest="command", required=True)

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

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if args.command == "pull":
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

    if args.command == "sample":
        # Mid-June can be a minors off-day / sparse tracking; mid-April is denser.
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

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
