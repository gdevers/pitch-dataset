"""Chadwick Bureau player ID register for cross-source joins."""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def pull_chadwick_register() -> pd.DataFrame:
    """Download the Chadwick player register (MLBAM ↔ FanGraphs ↔ BBRef)."""
    try:
        from pybaseball import chadwick_register
    except ImportError as exc:
        raise RuntimeError("pybaseball is required for the Chadwick register") from exc

    try:
        frame = chadwick_register()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Chadwick register download failed: {exc}") from exc

    if frame.empty:
        logger.warning("Chadwick register returned no rows")
        return frame

    out = frame.copy()
    for col in ("key_mlbam", "key_fangraphs", "key_bbref", "key_retro"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    return out
