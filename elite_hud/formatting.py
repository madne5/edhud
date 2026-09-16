"""Pure text formatting helpers.

Kept free of Qt imports so the HUD strings can be unit-tested headlessly.
"""

from __future__ import annotations

from .exobiology import Confidence


def format_credits(value: int) -> str:
    """Compact credit formatting: ``19_010_800`` -> ``'19.0M'``."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def format_countdown(seconds: float) -> str:
    """``MM:SS``, or ``H:MM:SS`` once the wait is over an hour.

    Rounds up so a scheduled jump never reads ``00:00`` while it is pending.
    """
    if seconds < 0:
        seconds = 0
    total = int(seconds + 0.999)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


CONFIDENCE_GLYPH = {
    Confidence.CONFIRMED: "star",
    Confidence.GUARANTEED: "gem",
    Confidence.POSSIBLE: "warning",
}

CONFIDENCE_LABEL = {
    Confidence.CONFIRMED: "точно",
    Confidence.GUARANTEED: "гарантированно",
    Confidence.POSSIBLE: "возможно",
}
