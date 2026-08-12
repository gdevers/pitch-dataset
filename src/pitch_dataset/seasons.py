"""Season calendars and defaults.

The 2026 MLB / MiLB season is the first-class default for this package.
"""

from __future__ import annotations

from datetime import date, timedelta

DEFAULT_SEASON = 2026

# Approximate regular-season windows used when only a year is supplied.
# End dates are clamped to today so in-season pulls stay current.
_SEASON_WINDOWS: dict[int, tuple[date, date]] = {
    2021: (date(2021, 4, 1), date(2021, 10, 15)),
    2022: (date(2022, 4, 7), date(2022, 10, 15)),
    2023: (date(2023, 3, 30), date(2023, 11, 1)),
    2024: (date(2024, 3, 20), date(2024, 11, 2)),
    2025: (date(2025, 3, 18), date(2025, 11, 2)),
    2026: (date(2026, 3, 20), date(2026, 11, 5)),
}

SUPPORTED_SEASONS = sorted(_SEASON_WINDOWS)


def season_date_range(
    season: int = DEFAULT_SEASON,
    *,
    start: date | str | None = None,
    end: date | str | None = None,
    as_of: date | None = None,
) -> tuple[date, date]:
    """Return inclusive start/end dates for a season pull.

    Defaults to the full 2026 window, clamped so ``end`` never exceeds ``as_of``
    (today by default). Explicit ``start`` / ``end`` override the calendar.
    """
    as_of = as_of or date.today()
    if season not in _SEASON_WINDOWS:
        raise ValueError(
            f"Unsupported season {season}. Supported: {SUPPORTED_SEASONS}"
        )

    cal_start, cal_end = _SEASON_WINDOWS[season]
    start_dt = _parse_date(start) if start else cal_start
    end_dt = _parse_date(end) if end else min(cal_end, as_of)

    if end_dt < start_dt:
        raise ValueError(f"Invalid range: start={start_dt} end={end_dt}")
    return start_dt, end_dt


def _parse_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def iter_date_chunks(
    start: date,
    end: date,
    *,
    chunk_days: int = 1,
) -> list[tuple[date, date]]:
    """Split an inclusive date range into chunks (default: one day each)."""
    if chunk_days < 1:
        raise ValueError("chunk_days must be >= 1")
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks
