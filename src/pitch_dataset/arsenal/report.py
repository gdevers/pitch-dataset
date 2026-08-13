"""Human-readable arsenal optimization reports."""

from __future__ import annotations

from pathlib import Path

from pitch_dataset.arsenal.optimize import PitcherRecommendation, SegmentRecommendation


def format_recommendation_report(
    recs: list[PitcherRecommendation] | PitcherRecommendation,
    *,
    title: str = "Pitch Arsenal Optimization Report",
    data_note: str | None = None,
) -> str:
    if isinstance(recs, PitcherRecommendation):
        recs = [recs]

    lines: list[str] = [f"# {title}", ""]
    if data_note:
        lines.extend([data_note, ""])

    lines.append(
        "Recommendations compare **actual usage** to a constrained optimal mix "
        "that minimizes predicted pitch-level xwOBA (lower is better for the pitcher), "
        "holding location/count/TTO/context fixed and only reallocating pitch-type share."
    )
    lines.append("")

    for rec in recs:
        lines.extend(_format_pitcher(rec))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_recommendation_report(
    recs: list[PitcherRecommendation] | PitcherRecommendation,
    path: Path | str,
    **kwargs,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_recommendation_report(recs, **kwargs), encoding="utf-8")
    return path


def _format_pitcher(rec: PitcherRecommendation) -> list[str]:
    lines = [
        f"## {rec.pitcher_name} (MLBAM {rec.pitcher_id})",
        "",
        f"- Pitches modeled: **{rec.n_pitches:,}**",
        f"- Arsenal: {', '.join(rec.arsenal)}",
        f"- Overall expected xwOBA: {_pct_xw(rec.overall_current_xwoba)} → "
        f"{_pct_xw(rec.overall_optimized_xwoba)} "
        f"(improvement **{_delta_xw(rec.expected_improvement_xwoba)}**)",
        f"- Overall expected RV/pitch: {rec.overall_current_rv:+.4f} → "
        f"{rec.overall_optimized_rv:+.4f} "
        f"({rec.expected_improvement_rv:+.4f})",
        "",
    ]

    # Highlight platoon segments first.
    platoon = [s for s in rec.segments if s.segment.startswith("vs ") and "|" not in s.segment]
    detail = [s for s in rec.segments if s not in platoon]

    if platoon:
        lines.append("### Platoon usage")
        lines.append("")
        for seg in platoon:
            lines.extend(_format_segment(seg))
            lines.append("")

    if detail:
        lines.append("### Count / situation detail")
        lines.append("")
        # Keep the most actionable count segments (largest |ΔxwOBA|).
        ranked = sorted(detail, key=lambda s: abs(s.expected_improvement_xwoba), reverse=True)
        for seg in ranked[:6]:
            lines.extend(_format_segment(seg, compact=True))
            lines.append("")

    if rec.pairing_notes:
        lines.append("### Arsenal pairing signals")
        lines.append("")
        for note in rec.pairing_notes:
            lines.append(f"- {note}")
        lines.append("")

    return lines


def _format_segment(seg: SegmentRecommendation, *, compact: bool = False) -> list[str]:
    header = f"#### {seg.segment}" if not compact else f"**{seg.segment}** ({seg.n_pitches} pitches)"
    lines = [
        header,
        "",
        f"Expected improvement: **{_delta_xw(seg.expected_improvement_xwoba)} xwOBA** "
        f"({seg.current_xwoba:.3f} → {seg.optimized_xwoba:.3f}); "
        f"n={seg.n_pitches}",
        "",
    ]
    # Show pitches with meaningful shifts.
    meaningful = [c for c in seg.changes if abs(c.delta_pct) >= 0.015]
    if not meaningful:
        meaningful = seg.changes[:3]
    for ch in meaningful:
        direction = "increase" if ch.delta_pct > 0 else "reduce"
        lines.append(
            f"- {direction.upper()} **{ch.pitch_type}** usage "
            f"from {_pct(ch.current_pct)} → {_pct(ch.recommended_pct)}"
        )
    return lines


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def _pct_xw(x: float) -> str:
    return f"{x:.3f}"


def _delta_xw(x: float) -> str:
    # Negative is good for pitcher.
    return f"{x:+.3f}"
